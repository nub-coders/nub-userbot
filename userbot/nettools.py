import ast
import asyncio
import math
import re
import time
import logging
import aiohttp
import speedtest
from pyrogram import Client, filters
from pyrogram.types import Message
from tools import (
    HARDCODED_PREFIXES, edit_or_reply, sudoers_filter, retry,
    get_args_from_caret
)

logger = logging.getLogger("userbot")

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
    msg = await edit_or_reply(message, f"🏓 **Pinging {url}...**\n\n⏳ Testing connection speed...")
    try:
        async with aiohttp.ClientSession() as session:
            start = time.perf_counter()
            async with session.get(url, timeout=5) as resp:
                elapsed = (time.perf_counter() - start) * 1000
                status = "✅ Excellent" if elapsed < 100 else "🟡 Good" if elapsed < 300 else "🔴 Slow"
                await msg.edit(f"✅ <b>Ping successful</b>\n\n⏱️ <b>Latency:</b> <code>{elapsed:.2f} ms</code>\n🔗 <b>URL:</b> <code>{url}</code>\n📊 <b>Status:</b> {status}")
    except Exception as e:
        await msg.edit(f"❌ <b>Ping failed</b>\n\n⚠️ <b>Error:</b> <code>{str(e)}</code>\n🔗 <b>URL:</b> <code>{url}</code>\n\n💡 Check if the URL is correct and accessible.")

# TCP connectivity test
@Client.on_message(filters.command("tcp", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def tcp_test(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 3:
        await edit_or_reply(message, f"❌ **Invalid format**\n\n💡 **Usage:** `{HARDCODED_PREFIXES[0]}tcp <host> <port>`\n📝 **Example:** `{HARDCODED_PREFIXES[0]}tcp google.com 443`")
        return
    host, port = args[1], int(args[2])
    msg = await edit_or_reply(message, f"🔌 **Testing TCP connection...**\n\n🎯 <b>Host:</b> <code>{host}</code>\n🔌 <b>Port:</b> <code>{port}</code>\n\n⏳ Please wait...")
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
        writer.close()
        await writer.wait_closed()
        await msg.edit(f"✅ <b>TCP connection successful</b>\n\n🎯 <b>Host:</b> <code>{host}</code>\n🔌 <b>Port:</b> <code>{port}</code>\n✅ <b>Status:</b> Reachable\n\n💡 The server is online and accepting connections.")
    except Exception as e:
        await msg.edit(f"❌ <b>TCP connection failed</b>\n\n🎯 <b>Host:</b> <code>{host}</code>\n🔌 <b>Port:</b> <code>{port}</code>\n⚠️ <b>Error:</b> <code>{str(e)}</code>\n\n💡 The server might be offline or blocking connections.")

# Async speedtest
@Client.on_message(filters.command("speed", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def async_speedtest(client: Client, message: Message):
    msg = await edit_or_reply(message, "📡 **Running speedtest...**\n\n⏳ This may take 30-60 seconds\n🔍 Finding best server...")
    try:
        loop = asyncio.get_event_loop()
        st = speedtest.Speedtest()
        await loop.run_in_executor(None, st.get_best_server)
        download = await loop.run_in_executor(None, st.download)
        upload = await loop.run_in_executor(None, st.upload)
        
        download_mbps = download / 1_000_000
        upload_mbps = upload / 1_000_000
        
        await msg.edit(f"📡 <b>Speedtest Results</b>\n\n"
                       f"🔽 <b>Download:</b> <code>{download_mbps:.2f} Mbps</code>\n"
                       f"🔼 <b>Upload:</b> <code>{upload_mbps:.2f} Mbps</code>\n\n"
                       f"📊 <b>Quality:</b> {'Excellent ✅' if download_mbps > 50 else 'Good 🟡' if download_mbps > 10 else 'Fair 🔴'}")
    except Exception as e:
        await msg.edit(f"❌ <b>Speedtest failed</b>\n\n⚠️ <b>Error:</b> <code>{str(e)}</code>\n\n💡 Check your internet connection and try again.")

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
            'factorial': math.factorial,
            'gcd': math.gcd,
        }
        
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

        # Evaluate the expression
        result = eval(compile(parsed, '<string>', 'eval'), {"__builtins__": {}}, safe_namespace)

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
