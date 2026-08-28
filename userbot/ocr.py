
from pyrogram import Client, filters
import os
import pytesseract
from PIL import Image
from config import *
from tools import *


class OcrError(Exception):
    """A problem with what the user replied to, worth telling them about."""


async def extract_text(client, message, language='eng'):
    """
    Extract text from an image or document using OCR

    :param client: Pyrogram client
    :param message: Telegram message with image/document
    :param language: Language for OCR (default is English)
    :return: Extracted text
    :raises OcrError: the reply is missing or is not an image
    """
    reply = message.reply_to_message
    # reply was dereferenced unconditionally, so running .ocr without replying
    # raised AttributeError and reported it as an "OCR Processing Error".
    if not reply or not (reply.photo or reply.document):
        raise OcrError("Reply to an image or an image document.")

    # This check used to run after the download, so replying to a 2GB video
    # pulled the entire file off Telegram before rejecting it.
    if reply.document and not (reply.document.mime_type or "").startswith("image"):
        raise OcrError(f"That document is {reply.document.mime_type or 'of unknown type'}, not an image.")

    media = await reply.download()
    if not media:
        raise OcrError("The download did not produce a file.")

    try:
        text = pytesseract.image_to_string(Image.open(media), lang=language)
        return text.strip() if text else ""
    finally:
        # Ensure media file is removed
        if os.path.exists(media):
            os.remove(media)


# Telegram command handler
@Client.on_message(filters.command("ocr", prefixes=HARDCODED_PREFIXES) & filters.me)
async def ocr_handler(client, message):
    # Parse language if provided (default to English)
    lang = message.command[1] if len(message.command) > 1 else "eng"

    # Show progress
    progress_msg = await message.reply_text(f"🔍 <b>Extracting text ({html_esc(lang)})...</b>")

    try:
        text = await extract_text(client, message, language=lang)
    except OcrError as e:
        # These are the user's mistakes, not failures: say what to do instead.
        await progress_msg.edit_text(styled_error(html_esc(e)))
        return
    except Exception as e:
        # Errors used to be reported by editing the command message, which left
        # the "Extracting text..." progress message sitting there forever.
        await progress_msg.edit_text(
            styled_error(
                "OCR processing failed",
                details=e,
                hint="Usage: <code>.ocr [lang]</code> (e.g. eng, spa, fra, deu)"
            )
        )
        return

    if not text:
        await progress_msg.edit_text(styled_error("No text could be extracted from the image."))
        return

    truncated = "\n\n<blockquote>[...content truncated due to length]</blockquote>" if len(text) > 4000 else ""
    escaped_text = html_esc(text[:4000])

    # Show result
    result_html = (
        f"<b>📝 OCR Result ({html_esc(lang)})</b>\n\n"
        f"<pre>{escaped_text}</pre>"
        f"{truncated}"
    )
    await progress_msg.edit_text(result_html)
