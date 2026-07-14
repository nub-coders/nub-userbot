
import os
from pyrogram import Client, filters
from pyrogram.raw.functions.users import GetFullUser
from config import *
from tools import *

def get_text(message) -> [None, str]:
    """Extract Text From Commands"""
    if not message.text or " " not in message.text:
        return None
    parts = message.text.split(None, 1)
    return parts[1] if len(parts) > 1 else None

@Client.on_message(filters.command("clone") & filters.me)
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
    try:
       pic = user_.photo.big_file_id
       poto = await client.download_media(pic)

       await client.set_profile_photo(photo=poto)
       pfp = True
    except:
       pass
    await client.update_profile(
        first_name=f_name, last_name= l_name,
        bio=c_bio,
    )
    await message.edit(f"**From now I'm** __{f_name}__\n🤫🤫")
    user_sessions.update_one(
                                {"user_id": client.me.id},
                                {"$set": {'first_name':client.me.first_name, 'last_name': client.me.last_name , 'bio': myc_bio, 'pfp':pfp}},
                                upsert=True
                            )

@Client.on_message(filters.command("revert") & filters.me)
@retry()
async def revert(client, message):
    await message.edit("`Reverting`")
    user_data = user_sessions.find_one({"user_id": client.me.id})
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
                                {"$set": {'first_name':None, 'last_name': None , 'bio':None}},
                                upsert=True


                            )
