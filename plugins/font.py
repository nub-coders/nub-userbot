
import re
from pyrogram import Client, filters
from fonts import *
from config import *
from tools import *

# Dictionary containing style names and their corresponding functions
styles = {
    'andalucia': andalucia,
    'arrows': arrows,
    'birds': birds,
    'bold_cool': bold_cool,
    'bold_gothic': bold_gothic,
    'bold_script': bold_script,
    'bubbles': bubbles,
    'circles': circles,
    'cloud': cloud,
    'comic': comic,
    'cool': cool,
    'dark_circle': dark_circle,
    'dark_square': dark_square,
    'frozen': frozen,
    'gothic': gothic,
    'happy': happy,
    'ladybug': ladybug,
    'manga': manga,
    'outline': outline,
    'rays': rays,
    'rvnes': rvnes,
    'sad': sad,
    'san': san,
    'script': script,
    'serief': serief,
    'sim': sim,
    'skyline': skyline,
    'slant': slant,
    'slant_san': slant_san,
    'slash': slash,
    'smallcap': smallcap,
    'special': special,
    'square': square,
    'stinky': stinky,
    'stop': stop,
    'strike': strike,
    'tiny': tiny,
    'typewriter': typewriter,
    'underline': underline
}

@Client.on_message(filters.command('fonts', prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def fontss(client, message):
    if message.text.startswith("/fonts"):
        return await message.edit_text("Check available font styles [here](https://telegra.ph/AVAILABLE-FONTS-STYLES-05-16-3)\n\nExample: _frozen hello")

    sender = client.me.id
    match = re.search(r'_(\S+)', message.text)
    try:
      if match:
        style = match.group(1)
        if style in styles:
          remaining_text = message.text.replace(f"_{style}", "", 1).strip()
          new_text = styles[style](remaining_text)
          await message.edit_text(f"`{new_text}` ", reply_markup=message.reply_markup)

    except Exception as e:
        await bot.send_message(sender, f"ERROR: {e}")
