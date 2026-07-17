import ast
import asyncio
import math
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
        
        # Parse the expression as an AST
        parsed = ast.parse(expression, mode='eval')

        # Check for dangerous operations
        for node in ast.walk(parsed):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id not in safe_namespace:
                    return await edit_or_reply(
                        message,
                        f"❌ **Unsafe operation detected**\n\n"
                        f"⚠️ Function `{node.func.id}` is not allowed\n\n"
                        f"💡 Use `{HARDCODED_PREFIXES[0]}calc` for available functions"
                    )

        # Evaluate the expression
        result = eval(compile(parsed, '<string>', 'eval'), {"__builtins__": {}}, safe_namespace)

        # Normalize float results
        if isinstance(result, float):
            result = int(result) if result.is_integer() else round(result, 10)

        await edit_or_reply(message, f"🧮 `{original_expression}` = `{result}`")

    except Exception as e:
        await edit_or_reply(
            message,
            f"❌ **Calculator error**\n\n"
            f"⚠️ **Error:** `{str(e)}`\n\n"
            f"💡 Use `{HARDCODED_PREFIXES[0]}calc` for help and examples"
        )
