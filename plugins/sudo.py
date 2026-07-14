import os
from pyrogram import Client, filters
from pyrogram.types import Message
from tools import *
from utils.message import Msg


async def resolve_target_id(message):
    """Resolve the target from a reply or a user-id argument.

    Returns a (user_id, user) tuple on success where ``user`` is the replied
    user object (or ``None`` when the id came from a command argument).
    On failure the appropriate error is sent and ``None`` is returned.
    """
    if message.reply_to_message:
        replied_msg = message.reply_to_message
        if replied_msg.from_user is not None:
            return replied_msg.from_user.id, replied_msg.from_user
        await message.reply("The replied message is not from a user.")
        return None

    command_parts = message.text.split()
    if len(command_parts) > 1:
        try:
            return int(command_parts[1]), None
        except ValueError:
            await message.reply("Please provide a valid user ID.")
            return None

    await message.reply("You need to reply to a message or provide a user ID.")
    return None


def _target_detail(user_id, user):
    """Build the card detail lines identifying the target."""
    if user is not None:
        user_name = user.first_name + (f" {user.last_name}" if user.last_name else "")
        return [f"User: {user_name}", f"ID: `{user_id}`"]
    return [f"User ID: `{user_id}`"]


@Client.on_message(filters.command("addsudo", prefixes=HARDCODED_PREFIXES) & filters.me)
async def add_to_sudo(client, message):
    resolved = await resolve_target_id(message)
    if resolved is None:
        return
    target_user_id, user = resolved

    # Check if target user is already admin (only when resolved from an id arg)
    if user is None and is_admin_user(target_user_id):
        return await message.reply(f"**This user is already an owner!**")

    # Get current sudo users
    users_data = user_sessions.find_one({"user_id": client.me.id})
    if not users_data:
        users_data = {}

    sudoers = users_data.get("sudoers", [])
    detail = _target_detail(target_user_id, user)

    if target_user_id not in sudoers:
        # Add user to sudoers
        user_sessions.update_one(
            {"user_id": client.me.id},
            {"$push": {"sudoers": target_user_id}},
            upsert=True
        )
        await message.edit(Msg.card("Sudo Access Granted", detail + ["Can now run sudo commands"], emoji=Msg.EMOJI_SUCCESS))
        SUDO[client.me.id].append(target_user_id)
    else:
        await message.edit(Msg.card("Already Has Sudo Access", detail + ["Already has sudo access"], emoji=Msg.EMOJI_INFO))


@Client.on_message(filters.command("rmsudo", prefixes=HARDCODED_PREFIXES) & filters.me)
async def remove_from_sudo(client, message):
    resolved = await resolve_target_id(message)
    if resolved is None:
        return
    target_user_id, user = resolved

    # Get current sudo users
    users_data = user_sessions.find_one({"user_id": client.me.id})
    if not users_data:
        if user is not None:
            return await message.edit(Msg.card("No Sudoers", ["No sudoers have been added yet"], emoji=Msg.EMOJI_INFO, footer="[prefix]addsudo to add users"))
        return await message.reply("No sudoers list found.")

    sudoers = users_data.get("sudoers", [])
    detail = _target_detail(target_user_id, user)

    if target_user_id in sudoers:
        # Remove user from sudoers
        user_sessions.update_one(
            {"user_id": client.me.id},
            {"$pull": {"sudoers": target_user_id}}
        )
        await message.edit(Msg.card("Sudo Access Revoked", detail + ["Removed from sudoers"], emoji=Msg.EMOJI_WARNING))
        SUDO[client.me.id].remove(target_user_id)
    else:
        await message.edit(Msg.card("Not in Sudo List", detail + ["Not in sudoers list"], emoji=Msg.EMOJI_INFO))


@Client.on_message(filters.command("sudolist", prefixes=HARDCODED_PREFIXES) & filters.me)
async def list_sudoers(client, message):
    # Get current sudo users
    users_data = user_sessions.find_one({"user_id": client.me.id})
    if not users_data:
        return await message.edit(
            f"No Sudoers\n\n"
            f"┃ No sudoers have been added yet\n"
            f"╰▸ [prefix]addsudo to add users"
        )

    sudoers = users_data.get("sudoers", [])

    if sudoers:
        sudoers_lines = [f"`{user_id}`" for user_id in sudoers]
        sudoers_lines.append(f"Total: {len(sudoers)} user(s)")
        await message.edit(Msg.card("Sudoers List", sudoers_lines, emoji=Msg.EMOJI_INFO))
    else:
        await message.edit(Msg.card("No Sudoers", ["List is empty"], emoji=Msg.EMOJI_INFO, footer="[prefix]addsudo to add users"))
