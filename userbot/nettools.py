import ast
import asyncio
import ipaddress
import math
import re
import socket
import time
import logging
from urllib.parse import urlparse
import aiohttp
import speedtest
from pyrogram import Client, filters
from pyrogram.types import Message
from tools import (
    HARDCODED_PREFIXES, edit_or_reply, sudoers_filter, retry,
    get_args_from_caret, styled_error
)

logger = logging.getLogger("userbot")


def _is_owner(message: Message) -> bool:
    """True when the account itself sent this, rather than a sudo user."""
    return bool(message.from_user and message.from_user.is_self)


async def _reject_internal_target(host: str):
    """Return a refusal string if `host` resolves anywhere off-limits, else None.

    .tcp and .pingurl reach out from the machine the userbot runs on, and both
    are open to sudo users. Unrestricted, that is a port scanner and a blind
    SSRF pointed at whatever the host can see but the internet cannot:
    127.0.0.1, the Docker bridge, a cloud instance-metadata endpoint. The owner
    is trusted with their own network; a sudo user is not, so they are held to
    public addresses.

    Every resolved address is checked, not just the first, so a hostname that
    answers with a loopback address is caught too.
    """
    if not host:
        return "No host to connect to."
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, None, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror as e:
        return f"Could not resolve {host}: {e}"
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if not address.is_global or address.is_loopback or address.is_private:
            return (
                f"{host} resolves to {address}, which is not a public address. "
                "Only the account owner may probe internal hosts."
            )
    return None

# Percentage notation handling for the calculator.
_PERCENT_OF_RE = re.compile(r'(\d+(?:\.\d+)?)\%\s*(?:of\s+)?(?=[\d(])')
_PERCENT_DELTA_RE = re.compile(r'([\+\-])\s*(\d+(?:\.\d+)?)\%(?!\s*[\d\(])')
_BARE_PERCENT_RE = re.compile(r'(\d+(?:\.\d+)?)\%')
_NUMBER_RE = re.compile(r'\d+(?:\.\d+)?')


def _paren_end(text: str, start: int) -> int:
    """Index just past the ')' closing the '(' at `start`; -1 if never closed."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _expand_percent_of(expression: str) -> str:
    """Rewrite "X% of Y" / "X% Y" / "X% (Y)" as ((X / 100) * Y).

    The right operand is taken by scanning rather than by a capture group: a
    group can only grab the opening '(' of a parenthesized operand, so
    "50% (10 + 30)" produced "((50 / 100) * ()10 + 30)" — the template's own
    ')' closed the captured '(' and the remainder dangled.
    """
    pos = 0
    while True:
        match = _PERCENT_OF_RE.search(expression, pos)
        if not match:
            return expression
        start = match.end()  # the lookahead guarantees a char here
        if expression[start] == '(':
            end = _paren_end(expression, start)
            if end == -1:
                # Unbalanced parens — leave it for ast.parse to report.
                pos = match.end()
                continue
        else:
            end = _NUMBER_RE.match(expression, start).end()
        prefix = f'(({match.group(1)} / 100) * '
        expression = (expression[:match.start()] + prefix
                      + expression[start:end] + ')' + expression[end:])
        # Resume inside the operand so nested percentages still expand.
        pos = match.start() + len(prefix)


def _base_start(prefix: str) -> int:
    """Index in `prefix` where the innermost open sub-expression begins.

    Scans back for an unclosed '(' so a percent inside parens uses only the
    enclosing group as its base: in "(100 + 10%) * 2" the base is "100", not
    "(100" — wrapping the latter would leave the parens unbalanced.
    """
    depth = 0
    for i in range(len(prefix) - 1, -1, -1):
        if prefix[i] == ')':
            depth += 1
        elif prefix[i] == '(':
            if depth == 0:
                return i + 1
            depth -= 1
    return 0


def _expand_percentages(expression: str) -> str:
    """Rewrite percentage notation into plain arithmetic.

    Handles three forms, in order:
      1. "X% of Y" / "X% Y" / "X% (Y)"  -> ((X / 100) * Y)
      2. "base + P%" / "base - P%"      -> (base) * (1 +/- P / 100)
      3. standalone "X%"                -> (X / 100)

    Rule 2 runs left-to-right, taking the whole expression accumulated so far
    as the base, so chains compound the way phone calculators do:
    "100 + 10% + 10%" -> 121, and "100 + 50 - 10%" -> 135 (10% of 150, not 50).
    A plain re.sub cannot do this — after one substitution the base ends in ')'
    rather than a digit, leaving a second pass nothing to anchor on, so the
    trailing term degrades to a bare "X%" (the 110.1 bug).

    The multiplicative form keeps the base once per term; restating it on both
    sides of the operator would double the text per term (716 chars for a
    5-term chain).

    Modulo is left alone: every rule requires the digit to sit immediately
    before '%', so the spaced form "15 % 4" never matches.
    """
    expression = _expand_percent_of(expression)

    pos = 0
    while True:
        match = _PERCENT_DELTA_RE.search(expression, pos)
        if not match:
            break
        start = _base_start(expression[:match.start()])
        base = expression[start:match.start()].strip()
        # Nothing to the left (e.g. a leading "-10%") — leave it to rule 3.
        if not base:
            pos = match.end()
            continue
        op, percent = match.group(1), match.group(2)
        rewritten = f'({base}) * (1 {op} {percent} / 100)'
        expression = expression[:start] + rewritten + expression[match.end():]
        pos = start + len(rewritten)

    return _BARE_PERCENT_RE.sub(r'(\1 / 100)', expression)


# HTTP ping (latency test)
@Client.on_message(filters.command("pingurl", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def http_ping(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    url = args[1] if len(args) > 1 else "https://google.com"
    if not _is_owner(message):
        refusal = await _reject_internal_target(urlparse(url).hostname)
        if refusal:
            return await edit_or_reply(message, styled_error("Refused", details=refusal))
    msg = await edit_or_reply(message, f"🏓 <b>Testing HTTP latency to {url}...</b>")
    try:
        async with aiohttp.ClientSession() as session:
            start = time.perf_counter()
            async with session.get(url, timeout=5) as resp:
                elapsed = (time.perf_counter() - start) * 1000
                status = "Excellent 🟢" if elapsed < 100 else "Good 🟡" if elapsed < 300 else "Slow 🔴"
                result_text = (
                    f"<b>🏓 HTTP Ping Result</b>\n\n"
                    f"<blockquote>\n"
                    f"<b>• Target:</b> <code>{url}</code>\n"
                    f"<b>• Latency:</b> <code>{elapsed:.2f} ms</code>\n"
                    f"<b>• Status:</b> {status}\n"
                    f"</blockquote>"
                )
                await msg.edit(result_text)
    except Exception as e:
        await msg.edit(styled_error(f"Ping failed: {e}", hint="Check if the URL is accessible and includes https://"))

# TCP connectivity test
@Client.on_message(filters.command("tcp", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def tcp_test(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 3:
        await edit_or_reply(message, styled_error("Invalid format", hint=f"Usage: <code>{HARDCODED_PREFIXES[0]}tcp &lt;host&gt; &lt;port&gt;</code>"))
        return
    host = args[1]
    # Parsed and range-checked here rather than inside the try below, where it
    # used to sit outside it: ".tcp example.com http" raised an unhandled
    # ValueError out of the handler instead of saying what was wrong.
    try:
        port = int(args[2])
    except ValueError:
        await edit_or_reply(message, styled_error(
            f"{args[2]!r} is not a port number",
            hint=f"Usage: <code>{HARDCODED_PREFIXES[0]}tcp &lt;host&gt; &lt;port&gt;</code>",
        ))
        return
    if not 1 <= port <= 65535:
        await edit_or_reply(message, styled_error(f"Port {port} is out of range", hint="Ports run from 1 to 65535."))
        return
    if not _is_owner(message):
        refusal = await _reject_internal_target(host)
        if refusal:
            return await edit_or_reply(message, styled_error("Refused", details=refusal))
    msg = await edit_or_reply(message, f"🔌 <b>Testing TCP connection to {host}:{port}...</b>")
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
        writer.close()
        await writer.wait_closed()
        result_text = (
            f"<b>🔌 TCP Test Result</b>\n\n"
            f"<blockquote>\n"
            f"<b>• Host:</b> <code>{host}</code>\n"
            f"<b>• Port:</b> <code>{port}</code>\n"
            f"<b>• Status:</b> Reachable 🟢\n"
            f"</blockquote>\n\n"
            f"<i>The remote host is online and accepting TCP sockets.</i>"
        )
        await msg.edit(result_text)
    except Exception as e:
        await msg.edit(styled_error(f"TCP connection failed: {e}", hint="The port may be closed, firewalled, or the host is offline."))

# Async speedtest
@Client.on_message(filters.command("speed", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def async_speedtest(client: Client, message: Message):
    msg = await edit_or_reply(message, "📡 <b>Running Speedtest...</b>\n\n⏳ Testing network throughput...")
    try:
        loop = asyncio.get_event_loop()
        st = speedtest.Speedtest()
        await loop.run_in_executor(None, st.get_best_server)
        download = await loop.run_in_executor(None, st.download)
        upload = await loop.run_in_executor(None, st.upload)

        download_mbps = download / 1_000_000
        upload_mbps = upload / 1_000_000
        quality = 'Excellent 🟢' if download_mbps > 50 else 'Good 🟡' if download_mbps > 10 else 'Fair 🔴'

        result_text = (
            f"<b>📡 Speedtest Results</b>\n\n"
            f"<blockquote>\n"
            f"<b>• Download:</b> <code>{download_mbps:.2f} Mbps</code>\n"
            f"<b>• Upload:</b> <code>{upload_mbps:.2f} Mbps</code>\n"
            f"<b>• Quality:</b> {quality}\n"
            f"</blockquote>"
        )
        await msg.edit(result_text)
    except Exception as e:
        await msg.edit(styled_error(f"Speedtest failed: {e}"))



# Calculator limits. The AST whitelist below decides what the calculator may
# *do*; these decide how much work it may do. Only two constructs in the allowed
# set can run unbounded -- "**" and factorial() -- and both are C loops that hold
# the GIL, so "2 ** 10**9" or "factorial(10**9)" freezes the entire userbot until
# it finishes or the machine runs out of memory. A thread would not help for the
# same reason. Everything else in the namespace is O(1) float arithmetic, and
# there is no way to build a list or a range, so bounding these two bounds the
# command.
_CALC_MAX_EXPRESSION = 1000     # characters
_CALC_MAX_POW_DIGITS = 5000     # ~5000-digit results compute instantly
_CALC_MAX_FACTORIAL = 5000      # 5000! is about 16k digits


class _CalcLimit(ValueError):
    """Raised when an expression asks for more work than the calculator allows."""


def _guarded_pow(base, exponent, modulus=None):
    """base ** exponent, refusing results too large to compute cheaply."""
    if modulus is not None:
        return pow(base, exponent, modulus)
    digits = None
    try:
        magnitude = abs(base)
        if magnitude > 1 and exponent > 0:
            digits = float(exponent) * math.log10(float(magnitude))
    except (TypeError, ValueError, OverflowError):
        # Not something whose size can be estimated -- a complex result, say.
        # Leave the decision to Python.
        digits = None
    if digits is not None and digits > _CALC_MAX_POW_DIGITS:
        raise _CalcLimit(
            f"result would have about {digits:.0f} digits; "
            f"the limit is {_CALC_MAX_POW_DIGITS}"
        )
    return base ** exponent


def _guarded_factorial(n):
    """math.factorial, refusing arguments that would take a visible age."""
    if isinstance(n, (int, float)) and n > _CALC_MAX_FACTORIAL:
        raise _CalcLimit(f"factorial argument above {_CALC_MAX_FACTORIAL} is not allowed")
    return math.factorial(n)


class _GuardPowers(ast.NodeTransformer):
    """Rewrite `a ** b` as a call to the size-checked helper.

    Run after validation, so the injected name cannot be reached by anyone
    typing it themselves -- at validation time it is not in the namespace.
    """

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Pow):
            return ast.Call(
                func=ast.Name(id="_calc_pow", ctx=ast.Load()),
                args=[node.left, node.right],
                keywords=[],
            )
        return node


# Calculator command
@Client.on_message(filters.command(["calc", "calculate"], prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def calculator(client: Client, message: Message):
    """Advanced calculator with support for mathematical expressions"""
    try:
        # Get the expression from command
        args = get_args_from_caret(message)
        
        if not args:
            help_text = """
🧮 **Calculator Help**

**Usage:** `{prefix}calc <expression>`

**Supported Operations:**
• Basic: `+`, `-`, `*`, `/`, `%`, `**` (power)
• Functions: `sqrt()`, `sin()`, `cos()`, `tan()`, `log()`, `abs()`
• Constants: `pi`, `e`

**Examples:**
• `{prefix}calc 2 + 2`
• `{prefix}calc sqrt(144)`
• `{prefix}calc 2 ** 8`
• `{prefix}calc sin(pi/2)`
• `{prefix}calc (5 + 3) * 2`
• `{prefix}calc log(100)`

**Advanced:**
• `{prefix}calc 15 % 4` (modulo)
• `{prefix}calc abs(-42)` (absolute value)
• `{prefix}calc pi * 2` (pi constant)
            """.format(prefix=HARDCODED_PREFIXES[0])
            return await edit_or_reply(message, help_text)
        
        # Join all arguments to form the expression
        expression = " ".join(args)
        original_expression = expression

        if len(expression) > _CALC_MAX_EXPRESSION:
            return await edit_or_reply(
                message,
                f"❌ **Expression too long**\n\n"
                f"⚠️ {len(expression)} characters; the limit is {_CALC_MAX_EXPRESSION}"
            )
        
        # Create a safe namespace with allowed functions and constants
        safe_namespace = {
            'abs': abs,
            'round': round,
            'min': min,
            'max': max,
            'sum': sum,
            'pow': pow,
            'sqrt': math.sqrt,
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'asin': math.asin,
            'acos': math.acos,
            'atan': math.atan,
            'sinh': math.sinh,
            'cosh': math.cosh,
            'tanh': math.tanh,
            'log': math.log,
            'log10': math.log10,
            'log2': math.log2,
            'exp': math.exp,
            'floor': math.floor,
            'ceil': math.ceil,
            'pi': math.pi,
            'e': math.e,
            'tau': math.tau,
            'degrees': math.degrees,
            'radians': math.radians,
            'factorial': _guarded_factorial,
            'gcd': math.gcd,
        }
        # pow() and factorial() are the size-checked versions; see the limits
        # above. Registered under their ordinary names so the whitelist check
        # below, and the help text, stay as they were.
        safe_namespace['pow'] = _guarded_pow
        
        # Replace common notation
        expression = expression.replace('^', '**')
        expression = expression.replace('×', '*')
        expression = expression.replace('÷', '/')

        expression = _expand_percentages(expression)
        
        # Parse the expression as an AST
        parsed = ast.parse(expression, mode='eval')

        # Whitelist of safe AST node types — anything else is rejected.
        _SAFE_NODES = (
            ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call,
            ast.Name, ast.Constant, ast.Load,
            # Arithmetic / comparison operators
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
            ast.Mod, ast.Pow, ast.USub, ast.UAdd,
            # Backwards-compat: ast.Num/Str still emitted by some Python versions
            *(x for x in (getattr(ast, 'Num', None), getattr(ast, 'Str', None)) if x),
        )

        for node in ast.walk(parsed):
            if not isinstance(node, _SAFE_NODES):
                return await edit_or_reply(
                    message,
                    f"❌ **Unsafe operation detected**\n\n"
                    f"⚠️ Expression contains disallowed construct: "
                    f"`{type(node).__name__}`\n\n"
                    f"💡 Use `{HARDCODED_PREFIXES[0]}calc` for available functions"
                )
            # For Call nodes, only allow direct name-based calls (e.g. sqrt(x)),
            # not attribute calls (e.g. obj.method()).
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name):
                    return await edit_or_reply(
                        message,
                        f"❌ **Unsafe operation detected**\n\n"
                        f"⚠️ Only direct function calls are allowed\n\n"
                        f"💡 Use `{HARDCODED_PREFIXES[0]}calc` for available functions"
                    )
                if node.func.id not in safe_namespace:
                    return await edit_or_reply(
                        message,
                        f"❌ **Unsafe operation detected**\n\n"
                        f"⚠️ Function `{node.func.id}` is not allowed\n\n"
                        f"💡 Use `{HARDCODED_PREFIXES[0]}calc` for available functions"
                    )

        # Evaluate the expression. The "**" operator is rewritten into a
        # size-checked call only now, after validation, so that nobody can reach
        # the helper by naming it: at validation time it is not in the namespace.
        parsed = ast.fix_missing_locations(_GuardPowers().visit(parsed))
        result = eval(
            compile(parsed, '<string>', 'eval'),
            {"__builtins__": {}},
            {**safe_namespace, "_calc_pow": _guarded_pow},
        )

        # Normalize float results. Round before the integer check: the
        # percentage rewrite divides by 100, so exact results arrive as
        # 110.00000000000001 and would otherwise render as "110.0".
        if isinstance(result, float):
            result = round(result, 10)
            if result.is_integer():
                result = int(result)

        await edit_or_reply(message, f"🧮 `{original_expression}` = `{result}`")

    except Exception as e:
        await edit_or_reply(
            message,
            f"❌ **Calculator error**\n\n"
            f"⚠️ **Error:** `{str(e)}`\n\n"
            f"💡 Use `{HARDCODED_PREFIXES[0]}calc` for help and examples"
        )
