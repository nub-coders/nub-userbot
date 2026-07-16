
from pyrogram import Client, filters
from pyrogram.types import Message
import os
import pytesseract
from PIL import Image
from config import *
from tools import *

async def extract_text(client, message, language='eng'):
    """
    Extract text from an image or document using OCR

    :param client: Pyrogram client
    :param message: Telegram message with image/document
    :param language: Language for OCR (default is English)
    :return: Extracted text
    """
    reply = message.reply_to_message
    if not (reply.photo or reply.document):
        return await message.edit("❗ Reply to an image/document")

    media = await reply.download()

    try:
        # Check if document is an image
        if reply.document and not reply.document.mime_type.startswith('image'):
            return await message.edit("❗ Document must be an image type")

        # Extract text with specified language
        text = pytesseract.image_to_string(Image.open(media), lang=language)

        return text.strip() if text else ""

    except Exception as e:
        await message.edit(f"❌ Error: {e}")
        return ""
    finally:
        # Ensure media file is removed
        if os.path.exists(media):
            os.remove(media)

# Telegram command handler
@Client.on_message(filters.command("ocr", prefixes=HARDCODED_PREFIXES) & filters.me)
async def ocr_handler(client, message):
    try:
        # Parse language if provided (default to English)
        lang = message.command[1] if len(message.command) > 1 else "eng"

        # Show progress
        progress_msg = await message.reply_text(f"🔍 Extracting text ({lang})...")

        # Process
        text = await extract_text(client, message, language=lang)

        # Show result
        await progress_msg.edit_text(
            f"📝 Extracted text ({lang}):\n\n{text[:4000]}" +
            ("\n[...truncated]" if len(text) > 4000 else "")
        )

    except Exception as e:
        await message.edit_text(
            f"⚠️ OCR Error\n"
            f"Usage: /ocr [lang]\n"
            f"Supported languages: eng, spa, fra, etc.\n"
            f"Error: {str(e)}"
        )

