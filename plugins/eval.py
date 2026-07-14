
import ast
import traceback
import sys
import inspect
from io import StringIO
import contextlib
import html
import asyncio
import textwrap
import time
import os
from pyrogram import Client, filters
from pyrogram.types import Message
import pyrogram
from config import *
from tools import *

# Message templates with proper HTML escaping
RUNNING = "<b>Eval Expression:</b>\n<pre>{}</pre>\n<b>Running...</b>"
ERROR = "<b>Eval Expression:</b>\n<pre>{}</pre>\n<b>Error:</b>\n<pre>{}</pre>"
SUCCESS = "<b>Eval Expression:</b>\n<pre>{}</pre>\n<b>Success</b>"
RESULT = "<b>Eval Expression:</b>\n<pre>{}</pre>\n<b>Result:</b>\n<pre>{}</pre>"

@Client.on_message(filters.me & filters.command('eval', prefixes='^'))
@retry()
async def eval_expression(client, message):
    
    # Extract the raw text after the command prefix
    if not message.text or len(message.command) < 2:
        await message.reply("Please provide code to evaluate.")
        return
    
    # Get full text after command
    if " " in message.text:
        full_command = message.text.split(" ", 1)[1]
    else:
        full_command = ""
    
    # Handle code blocks if present
    if full_command.startswith("```python") and full_command.endswith("```"):
        code = full_command[10:-3].strip()
    elif full_command.startswith("```") and full_command.endswith("```"):
        code = full_command[3:-3].strip()
    else:
        code = full_command
    
    if not code:
        await message.reply("Please provide code to evaluate.")
        return
    
    # Send initial "running" message
    response_msg = await message.reply(RUNNING.format(html.escape(code)))
    
    # Prepare globals and locals for execution
    globals_dict = globals().copy()
    # Add important modules and client objects to globals
    globals_dict.update({
        'client': client,
        'message': message,
        'asyncio': asyncio,
        'inspect': inspect,
    })
    
    locals_dict = {}
    
    # Capture stdout and stderr
    stdout = StringIO()
    stderr = StringIO()
    
    try:
        # Wrap code in async function for execution
        wrapped_code = f"""
async def __async_exec_function():
    __result = None
{textwrap.indent(code, '    ')}
    return __result
"""
        
        # Execute the code
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(wrapped_code, globals_dict, locals_dict)
            result = await locals_dict['__async_exec_function']()
        
        # Collect output
        stdout_output = stdout.getvalue()
        stderr_output = stderr.getvalue()
        
        # Format the final output
        output = ""
        if stdout_output:
            output += f"STDOUT:\n{stdout_output}\n"
        if stderr_output:
            output += f"STDERR:\n{stderr_output}\n"
        if result is not None:
            output += f"RETURN:\n{result}"
        
        # Check if the output is empty
        if not output:
            try:
                await client.edit_message_text(
                    chat_id=response_msg.chat.id,
                    message_id=response_msg.id,
                    text=SUCCESS.format(html.escape(code))
                )
            except pyrogram.errors.exceptions.bad_request_400.MessageTooLong:
                # Even the code is too long for display
                await handle_long_message(client, response_msg, code, "Success, no output")
            return
            
        # Try to send the full result
        try:
            await client.edit_message_text(
                chat_id=response_msg.chat.id,
                message_id=response_msg.id,
                text=RESULT.format(html.escape(code), html.escape(output))
            )
        except pyrogram.errors.exceptions.bad_request_400.MessageTooLong:
            # Message is too long, handle it differently
            await handle_long_message(client, response_msg, code, output)
            
    except Exception as e:
        # Get full traceback for errors
        error_text = traceback.format_exc()
        try:
            await client.edit_message_text(
                chat_id=response_msg.chat.id,
                message_id=response_msg.id,
                text=ERROR.format(html.escape(code), html.escape(error_text))
            )
        except pyrogram.errors.exceptions.bad_request_400.MessageTooLong:
            # Error message is too long
            await handle_long_message(client, response_msg, code, error_text, is_error=True)

async def handle_long_message(client, original_msg, code, output, is_error=False):
    """Output too long for a Telegram message — upload it as a text file."""
    try:
        # Create a temporary file
        file_name = f"eval_{'error' if is_error else 'output'}_{int(time.time())}.txt"
        with open(file_name, "w", encoding="utf-8") as file:
            file.write(f"Eval Expression:\n{code}\n\n")
            file.write(f"{'Error' if is_error else 'Result'}:\n{output}")
        
        # Edit message to indicate file upload
        await client.edit_message_text(
            chat_id=original_msg.chat.id,
            message_id=original_msg.id,
            text=f"<b>Eval Expression:</b>\n<pre>{html.escape(code[:500])}{'...' if len(code) > 500 else ''}</pre>\n<b>{'Error' if is_error else 'Result'} too large, uploading as file...</b>"
        )
        
        # Send the file
        await client.send_document(
            chat_id=original_msg.chat.id,
            document=file_name,
            caption=f"{'Error' if is_error else 'Result'} output for eval command"
        )
        
        # Clean up
        os.remove(file_name)
        
    except Exception as file_error:
        # Last resort if everything fails
        await client.edit_message_text(
            chat_id=original_msg.chat.id,
            message_id=original_msg.id,
            text=f"<b>Eval Expression:</b>\n<pre>{html.escape(code[:500])}{'...' if len(code) > 500 else ''}</pre>\n<b>Output too large to display and file upload failed:</b> {str(file_error)}"
        )
