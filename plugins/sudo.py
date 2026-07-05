import os
from pyrogram import Client, filters
from pyrogram.types import Message
from tools import *
from utils.message import Msg

@Client.on_message(filters.command("addsudo", prefixes=HARDCODED_PREFIXES) & filters.me)
async def add_to_sudo(client, message):
    if message.reply_to_message:
        replied_msg = message.reply_to_message
        if replied_msg.from_user is not None:
            replied_user_id = replied_msg.from_user.id

            # Get current sudo users
            users_data = user_sessions.find_one({"user_id": client.me.id})
            if not users_data:
                users_data = {}

            sudoers = users_data.get("sudoers", [])

            if replied_user_id not in sudoers:
                # Add user to sudoers
                user_sessions.update_one(
                    {"user_id": client.me.id},
                    {"$push": {"sudoers": replied_user_id}},
                    upsert=True
                )
                user = replied_msg.from_user
                user_name = user.first_name + (f" {user.last_name}" if user.last_name else "")
                await message.edit(Msg.card("Sudo Access Granted", [f"User: {user_name}", f"ID: `{replied_user_id}`", "Can now run sudo commands"], emoji=Msg.EMOJI_SUCCESS))
                SUDO[client.me.id].append(replied_user_id)

            else:
                user = replied_msg.from_user
                user_name = user.first_name + (f" {user.last_name}" if user.last_name else "")
                await message.edit(Msg.card("Already Has Sudo Access", [f"User: {user_name}", f"ID: `{replied_user_id}`", "Already has sudo access"], emoji=Msg.EMOJI_INFO))
        else:
            await message.reply("The replied message is not from a user.")
    else:
        # Handle command with user ID
        command_parts = message.text.split()
        if len(command_parts) > 1:
            try:
                target_user_id = int(command_parts[1])

                # Check if target user is already admin
                if is_admin_user(target_user_id):
                    return await message.reply(f"**This user is already an owner!**")

                # Get current sudo users
                users_data = user_sessions.find_one({"user_id": client.me.id})
                if not users_data:
                    users_data = {}

                sudoers = users_data.get("sudoers", [])

                if target_user_id not in sudoers:
                    # Add user to sudoers
                    user_sessions.update_one(
                        {"user_id": client.me.id},
                        {"$push": {"sudoers": target_user_id}},
                        upsert=True
                    )
                    await message.edit(
                        Msg.card("Sudo Access Granted", [f"User ID: `{target_user_id}`", "Can now run sudo commands"], emoji=Msg.EMOJI_SUCCESS)
                    )

                    SUDO[client.me.id].append(target_user_id)

                else:
                    await message.edit(Msg.card("Already Has Sudo Access", [f"User ID: `{target_user_id}`", "Already has sudo access"], emoji=Msg.EMOJI_INFO))
            except ValueError:
                await message.reply("Please provide a valid user ID.")
        else:
            await message.reply("You need to reply to a message or provide a user ID.")


@Client.on_message(filters.command("rmsudo", prefixes=HARDCODED_PREFIXES) & filters.me)
async def remove_from_sudo(client, message):
    if message.reply_to_message:
        replied_msg = message.reply_to_message
        if replied_msg.from_user is not None:
            replied_user_id = replied_msg.from_user.id

            # Get current sudo users
            users_data = user_sessions.find_one({"user_id": client.me.id})
            if not users_data:
                return await message.edit(Msg.card("No Sudoers", ["No sudoers have been added yet"], emoji=Msg.EMOJI_INFO, footer="[prefix]addsudo to add users"))

            sudoers = users_data.get("sudoers", [])

            if replied_user_id in sudoers:
                # Remove user from sudoers
                user_sessions.update_one(
                    {"user_id": client.me.id},
                    {"$pull": {"sudoers": replied_user_id}}
                )
                user = replied_msg.from_user
                user_name = user.first_name + (f" {user.last_name}" if user.last_name else "")
                await message.edit(Msg.card("Sudo Access Revoked", [f"User: {user_name}", f"ID: `{replied_user_id}`", "Removed from sudoers"], emoji=Msg.EMOJI_WARNING))
                SUDO[client.me.id].remove(replied_user_id)
            else:
                user = replied_msg.from_user
                user_name = user.first_name + (f" {user.last_name}" if user.last_name else "")
                await message.edit(Msg.card("Not in Sudo List", [f"User: {user_name}", f"ID: `{replied_user_id}`", "Not in sudoers list"], emoji=Msg.EMOJI_INFO))
        else:
            await message.reply("The replied message is not from a user.")
    else:
        # Handle command with user ID
        command_parts = message.text.split()
        if len(command_parts) > 1:
            try:
                target_user_id = int(command_parts[1])

                # Get current sudo users
                users_data = user_sessions.find_one({"user_id": client.me.id})
                if not users_data:
                    return await message.reply("No sudoers list found.")

                sudoers = users_data.get("sudoers", [])

                if target_user_id in sudoers:
                    # Remove user from sudoers
                    user_sessions.update_one(
                        {"user_id": client.me.id},
                        {"$pull": {"sudoers": target_user_id}}
                    )
                    await message.edit(
                        Msg.card("Sudo Access Revoked", [f"User ID: `{target_user_id}`", "Removed from sudoers"], emoji=Msg.EMOJI_WARNING)
                    )
                    SUDO[client.me.id].remove(target_user_id)
                else:
                    await message.edit(Msg.card("Not in Sudo List", [f"User ID: `{target_user_id}`", "Not in sudoers list"], emoji=Msg.EMOJI_INFO))
            except ValueError:
                await message.reply("Please provide a valid user ID.")
        else:
            await message.reply("You need to reply to a message or provide a user ID.")


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
