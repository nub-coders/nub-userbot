
import logging
from config import *
from tools import *
from pyrogram import Client

# Configure the logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
)

# Create a logger object
logger = logging.getLogger("userbot")
import os
from random import randint
from pyrogram import filters, enums
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.messages import GetFullChat
from pyrogram.raw.functions.phone import CreateGroupCall, DiscardGroupCall
from pyrogram.raw.types import InputGroupCall, InputPeerChannel, InputPeerChat

current_dir = os.getcwd()








def get_arg(message):
    msg = cmd_text(message)
    if len(msg) < 2:
        return ""
    msg = msg.replace(" ", "", 1) if msg[1] == " " else msg
    split = msg[1:].replace("\n", " \n").split(" ")
    if " ".join(split[1:]).strip() == "":
        return ""
    return " ".join(split[1:])

@Client.on_message(filters.command("vc1", prefixes=HARDCODED_PREFIXES) & filters.me & filters.group)
@retry()
async def opengc(client, message):
    vctitle = get_arg(message)
    # `flags` was compared against ChatType.CHANNEL, but it held a string and
    # ChatType.CHANNEL is an enum member, so the comparison was always False;
    # the branch it guarded assigned chat.title (a string) to chat_id, which
    # resolve_peer cannot use. The chat id is always the right peer here.
    chat_id = message.chat.id
    try:
        if not vctitle:
            await client.invoke(
CreateGroupCall(
                    peer=(await client.resolve_peer(chat_id)),
                    random_id=randint(10000, 999999999),
            )
)
        else:
            await client.invoke(
                CreateGroupCall(
                    peer=(await client.resolve_peer(chat_id)),
                    random_id=randint(10000, 999999999),
                    title=vctitle,
                )
            )
        title_info = f" with title '<code>{html_esc(vctitle)}</code>'" if vctitle else ""
        await message.edit(styled_success(f"Group Voice Chat started{title_info}."))
    except Exception as e:
        logger.error(f"Failed to start group call: {e}")
        await message.edit(styled_error("Failed to start the group call.", details=str(e)))


@Client.on_message(filters.command("vc0", prefixes=HARDCODED_PREFIXES) & filters.me & filters.group)
@retry()
async def end_group_call(client, message):
    """End the active group call in the chat."""
    try:
        chat_peer = await client.resolve_peer(message.chat.id)

        if isinstance(chat_peer, (InputPeerChannel, InputPeerChat)):
            if isinstance(chat_peer, InputPeerChannel):
                full_chat = (await client.invoke(GetFullChannel(channel=chat_peer))).full_chat
            elif isinstance(chat_peer, InputPeerChat):
                full_chat = (await client.invoke(GetFullChat(chat_id=chat_peer.chat_id))).full_chat

            if full_chat is not None:
                group_call = full_chat.call
                if group_call is not None:
                    await client.invoke(
                        DiscardGroupCall(call=InputGroupCall(id=group_call.id, access_hash=group_call.access_hash))
                    )
                    await message.edit_text(styled_success("Group Voice Chat has been ended."))
                    return
        await message.edit_text(styled_error("No active group call found in this chat."))
    except Exception as e:
        logger.warning(f"End group call failed: {e}")
        await message.edit_text(styled_error("Failed to end the group call.", details=str(e)))





