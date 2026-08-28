
import os
import logging
from pyrogram import Client, filters
from pyrogram.raw.functions.users import GetFullUser
from config import *
from tools import *

logger = logging.getLogger("clone")

@Client.on_message(filters.command("clone", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def clone(client, message):
    text = get_text(message)
    op = await message.edit_text("`Cloning`")
    userk = get_user(message, text)[0]
    user_ = await client.get_users(userk)
    if os.path.exists(admin_file):
         with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            if user_.id in admin_ids:
                 return await op.edit("You are fucking requesting me to make clone of my lord and my creator.\nSo Iwon't...**Fuck off!!**")

    if not user_:
        await op.edit("`To Whome i should clone with`")
        return

    get_bio = await client.get_chat(user_.id)
    f_name = user_.first_name
    l_name = user_.last_name
    user_det = await client.invoke(GetFullUser(id =await client.resolve_peer(user_.id)))
    full_user = user_det.full_user
    c_bio = full_user.about
    my_det = await client.invoke(GetFullUser(id =await client.resolve_peer(client.me.id)))
    my_full_user = my_det.full_user
    myc_bio = my_full_user.about
    pfp = False
    poto = None
    try:
       pic = user_.photo.big_file_id
       poto = await client.download_media(pic)

       await client.set_profile_photo(photo=poto)
       pfp = True
    except Exception as e:
       logger.warning(f"clone: setting profile photo failed: {e}")
    finally:
       # The download landed in the working directory; without this every
       # .clone left another photo_*.jpg behind forever.
       if poto and os.path.exists(poto):
           try:
               os.remove(poto)
           except OSError as e:
               logger.warning(f"clone: could not remove {poto}: {e}")
    await client.update_profile(
        first_name=f_name, last_name= l_name,
        bio=c_bio,
    )
    # Escaped: f_name is a stranger's display name and this goes out under a
    # parse mode that also processes HTML.
    await message.edit(f"**From now I'm** __{html_esc(f_name)}__\n🤫🤫")
    # Only back up the real identity once. Cloning twice in a row used to
    # overwrite the backup with clone #1's name, so .revert restored the wrong
    # person -- and the original name was gone for good.
    existing = user_sessions.find_one({"user_id": client.me.id}) or {}
    if existing.get("first_name"):
        logger.info("clone: identity backup already present, keeping the original")
    else:
        user_sessions.update_one(
                                    {"user_id": client.me.id},
                                    {"$set": {'first_name':client.me.first_name, 'last_name': client.me.last_name , 'bio': myc_bio, 'pfp':pfp}},
                                    upsert=True
                                )

@Client.on_message(filters.command("revert", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def revert(client, message):
    await message.edit("`Reverting`")
    user_data = user_sessions.find_one({"user_id": client.me.id}) or {}
    f_name = user_data.get('first_name',None)
    if not f_name:
       await message.delete()
       return await bot.send_message(client.me.id,f"ERROR: Not cloned anyone yet")
    l_name = user_data.get('last_name',None)
    c_bio = user_data.get('bio',None)
    pfpile = user_data.get('pfp',None)
    # Get ur Name back[B
    await client.update_profile(
        first_name=f_name, last_name= l_name,
        bio=c_bio,
    )
    # Delte first photo to get ur identify
    if pfpile:
       photos = [p async for p in client.get_chat_photos("me")]
       await client.delete_profile_photos(photos[0].file_id)
    await message.edit("`The leader is back!`")
    user_sessions.update_one(
                                {"user_id": client.me.id},
                                {"$set": {'first_name':None, 'last_name': None , 'bio':None, 'pfp':False}},
                                upsert=True


                            )
