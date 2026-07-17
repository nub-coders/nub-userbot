
import os
import time
import requests
from pyrogram import Client, filters
from pyrogram.errors import ChatForwardsRestricted, FileReferenceExpired
from convopyro import Conversation, listen_message
from config import *
from tools import *

current_dir = ggg

# Pyrogram client setup
create_channel_filter = filters.create(
    lambda _, client, message: (
        message.chat
        and message.chat.id in getuser_data(client.me.id).get("channel", [])
    )
)

@Client.on_message(create_channel_filter)
@retry()
async def forward_message_handler(client, message):
        sender = client.me.id
        if getattr(message, 'service', None):
            return
        session_name = f'user_{sender}'
        user_dir = f"{ggg}/{session_name}"
        os.makedirs(user_dir, exist_ok=True)
        channel_name = message.chat.title
        channel_username = f"@{message.chat.username}" if message.chat.username else ""
        if message.chat.username:
                            message_link = f"https://t.me/{message.chat.username}/{message.id}"
        else:
                          message_id_str = str(message.chat.id).replace('-100', '')
                          message_link = f"https://t.me/c/{message_id_str}/{message.id}"
        channel_details = f"<b>{channel_name}</b> {channel_username} <a href='{message_link}'>Link to message</a>"
        try:
           mess=await message.copy(app.me.username)
           await app.send_message(chat_id=sender,text=channel_details,reply_to_message_id=mess.id)
        except (ChatForwardsRestricted, FileReferenceExpired):
           if message.media:
                        timer = Timer()
                        async def progress_bar(current, total,start_time=time.time()):
                         if timer.can_send() and total != 0:  # Add a check to ensure total is not zero
                           progress_percent = current * 100 / total
                           filename=message.media.name
                           progress_message = f"{type_of} {filename}: {progress_percent:.2f}%\n"

            # Calculate progress bar length
                           progress_bar_length = 20
                           num_ticks = int(progress_percent / (100 / progress_bar_length))
                           progress_bar_text = '█' * num_ticks + '░' * (progress_bar_length - num_ticks)


          # Calculate speed in MB/s
                           elapsed_time = time.time() - start_time
                           speed = current / (elapsed_time * 1024 * 1024)
                           progress_message += f"Speed: {speed:.2f} MB/s\n"

              # C alculate estimated time left to complete
                           time_left = (total - current) / (speed * 1024 * 1024) if speed != 0 else 0  # C>
                           progress_message += f"Time left: {time_left:.2f} seconds\n"
          # Display current size and total size
                           progress_message += f"Size: {current / (1024 * 1024):.2f} MB / {total / (1024 * 1024):.2f} MB"

          # Combine progress bar and message
                           progress_message += f"\n[{progress_bar_text}]"
             # Create a message with HTML formatting for better appearance
                           message_text = f"{progress_message}"
                           try:
                              if random.choices([True, False], weights=[1, 99])[0]:
                                await bot.edit_message(msg,message_text)
                           except Exception as e:
                              print(e)
                        msg = await bot.send_message(sender, "Downloading media/document......")
                        type_of="Downloading"
                        file_path=await message.download(f"{user_dir}/" ,progress=progress_bar)
                        file_extension = file_path.split('.')[-1]
                        type_of= "Uploading"
                        channel_name = message.chat.title
                        channel_username = f"@{message.chat.username}" if message.chat.username else ""
                        if message.chat.username:
                            message_link = f"https://t.me/{message.chat.username}/{message.id}"
                        else:
                          message_id_str = str(message.chat.id).replace('-100', '')
                          message_link = f"https://t.me/c/{message_id_str}/{message.id}"
                        channel_details = f"<b>{channel_name}</b> {channel_username} <a href='{message_link}'>Link to message</a>"

                        caption = f"<br><br>{message.text if message.caption is None else message.caption}\n\n{channel_details}"

                        if os.path.getsize(file_path) <= 2100000000:
                          if file_extension in ['jpg', 'jpeg', 'png', 'gif']:
                            await app.send_photo(chat_id=sender, photo=file_path, caption=caption,progress=progress_bar)
                          elif file_extension in ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a']:
                            await app.send_audio(chat_id=sender, audio=file_path, caption=caption ,progress=progress_bar)
                          elif file_extension in ['mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv']:
                            thumb_path = f"{file_path}_thumb.jpg"
                            generate_thumbnail(file_path, thumb_path)
                            duration=with_opencv(file_path)
                            await app.send_video(chat_id=sender, video=file_path, caption=caption ,progress=progress_bar,duration=duration,thumb=thumb_path)
                            os.remove(thumb_path)
                          else:
                            await app.send_document( sender, file_path, caption=caption ,progress=progress_bar)
                        else:
                         await big_file(msg,sender,file_path)
                        await msg.delete()
                        os.remove(file_path)
           else:
                 await bot.send_message(sender,message.text)
