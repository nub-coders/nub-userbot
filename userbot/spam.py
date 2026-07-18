
from pyrogram.errors.exceptions import PeerFlood, UserRestricted
from pyrogram.enums import ChatMembersFilter, UserStatus
from config import *
from tools import *

ggg = os.getcwd()

# Configure the logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
)
logger = logging.getLogger("spam")

spam_chats = []

def get_arg(message) -> [None, str]:
    """Extract Text From Commands"""
    text_to_return = message.text
    if message.text is None:
        return None
    if " " in text_to_return:
        try:
            return message.text.split(None, 1)[1]
        except IndexError:
            return None
    else:
        return None



# Check if user was active in last 3 days
def is_active_user(user):
    return user.status in (UserStatus.ONLINE, UserStatus.RECENTLY, UserStatus.LAST_WEEK)

@Client.on_message(filters.command(["spam", "statspam", "slowspam"], prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def spam(client, message):
    if message.chat.id==-1001806816712 or is_admin(message.chat.id):
       return await message.edit_text("Who the hell are you trying to spam in my owner's/lord's Chat/Group\n\n**Fuck off!!!**")
    if len(message.text.split()) <3 :
       return await bot.send_message(client.me.id, f"**USAGE EXAMPLE:** /spam 5 hello`")
    try:
        amount = int(message.command[1])
    except ValueError:
        return await bot.send_message(client.me.id, "**ERROR:** Count must be a number.")
    if amount < 1 or amount > 500:
        return await bot.send_message(client.me.id, "**ERROR:** Count must be between 1 and 500.")
    text = " ".join(message.command[2:])
    spam_type = message.command[0]

    await message.delete()

    for msg in range(amount):
        try:
          if message.reply_to_message:
            sent = await message.reply_to_message.reply(text)
          else:
            sent = await client.send_message(message.chat.id, text)
        except FloodWait as e:
                    await asyncio.sleep(e.value)
        except Exception as e:
                mg = await bot.send_message(client.me.id, f"**ERROR:** `{e}`")
                await asyncio.sleep(3)
                break
        if spam_type == "statspam":
            await asyncio.sleep(0.1)
            await sent.delete()
        elif spam_type == "spam":
            await asyncio.sleep(0.1)
        elif spam_type == "slowspam":
            await asyncio.sleep(2)

async def spam_text(
    client: Client,
    chat_id: int,
    to_spam: str,
    count: int,
    reply_to: int,
    delay: float,
    event: asyncio.Event,
):
    for _ in range(count):
        await client.send_message(
                chat_id,
                to_spam,
                disable_web_page_preview=True,
                reply_to_message_id=reply_to,
            )
        if delay:
            await asyncio.sleep(delay)

@Client.on_message(filters.command("dspam", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def delaySpam(client, message):
    if len(message.command) < 4:
        return await message.edit( "Atleast give me something to spam.")

    reply_to = message.reply_to_message.id if message.reply_to_message else None
    try:
        count = int(message.command[1])
    except ValueError:
        return await message.edit("Give me a valid count number(float) to spam.")

    try:
        delay = float(message.command[2])
    except ValueError:
        return await message.edit( "Give me a valid delay(int) to spam.")

    to_spam = message.text.split(" ", 3)[3].strip()
    event = asyncio.Event()
    task = asyncio.create_task(
        spam_text(client, message.chat.id, to_spam, count, reply_to, delay, event)
    )

    await message.delete()
    await task

@Client.on_message(filters.command("fastspam", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def fastspam(client, message):
    if message.chat.id==-1001806816712 or is_admin(message.chat.id):
       return await message.edit_text("Who the hell are you trying to spam in my owner's/lord's Chat/Group\n\n**Fuck off!!!**")
    if len(message.text.split()) <3 :
       return await bot.send_message(client.me.id, f"**USAGE EXAMPLE:** /spam 5 hello`")
    try:
        amount = int(message.command[1])
    except ValueError:
        return await bot.send_message(client.me.id, "**ERROR:** Count must be a number.")
    if amount < 1 or amount > 500:
        return await bot.send_message(client.me.id, "**ERROR:** Count must be between 1 and 500.")
    text = " ".join(message.command[2:])

    await message.delete()

    tasks = []
    for msg in range(amount):
        try:
            if message.reply_to_message:
                task = asyncio.create_task(message.reply_to_message.reply(text))
            else:
                task = asyncio.create_task(client.send_message(message.chat.id, text))
            tasks.append(task)
        except FloodWait as e:
                    await asyncio.sleep(e.value)

        except Exception as e:
            mg = await bot.send_message(client.me.id, f"ERROR: {e}")
            await asyncio.sleep(3)
            break
    await asyncio.wait(tasks)

@Client.on_message(filters.command(["tagall","tagadmins","tagactive","tagactiveonly","tagevery"], prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def mentionall(client, message):
    await message.delete()
    chat_id = message.chat.id
    
    # Get the command type
    cmd = message.command[0].lower()
    
    # Get replied message or arguments
    direp = message.reply_to_message
    args = get_arg(message)
    
    if not direp and not args:
        return await message.reply("**Give a message or reply to a message!**")
    
    # Add chat to active tagging list
    if chat_id not in spam_chats:
        spam_chats.append(chat_id)
    
    # Initialize counters
    usrnum = 0
    usrtxt = ""
    
    try:
        chat_members = []
        admins = []
        
        # First get all admins to filter them later if needed
        async for admin in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
            admins.append(admin.user.id)
        
        # Define filtering strategy based on command
        if cmd == "tagall":
            # All users including admins and owner
            async for usr in client.get_chat_members(chat_id):
                chat_members.append(usr)
                
        elif cmd == "tagadmins":
            # Only admins and owner
            async for usr in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
                chat_members.append(usr)
                
        elif cmd == "tagactive":
            # All active users including admins and owner
            async for usr in client.get_chat_members(chat_id, filter=ChatMembersFilter.RECENT):
                if is_active_user(usr.user):
                    chat_members.append(usr)
                    
        elif cmd == "tagactiveonly":
            # All active users excluding admins and owner
            async for usr in client.get_chat_members(chat_id, filter=ChatMembersFilter.RECENT):
                if is_active_user(usr.user) and usr.user.id not in admins:
                    chat_members.append(usr)
                    
        elif cmd == "tagevery":
            # All users excluding admins and owner
            async for usr in client.get_chat_members(chat_id):
                if usr.user.id not in admins:
                    chat_members.append(usr)
        
        # Process the filtered members
        for usr in chat_members:
            if chat_id not in spam_chats:
                break
                
            usrnum += 1
            usrtxt += f"[{usr.user.first_name}](tg://user?id={usr.user.id}), "
            
            if usrnum == 1:
                if args:
                    txt = f"{args}\n{usrtxt}"
                    await client.send_message(chat_id, txt)
                elif direp:
                    await direp.reply(usrtxt)
                
                await asyncio.sleep(5)  # Avoid flood limits
                usrnum = 0
                usrtxt = ""
        
        # Send any remaining users
        if usrnum > 0:
            if args:
                txt = f"{args}\n{usrtxt}"
                await client.send_message(chat_id, txt)
            elif direp:
                await direp.reply(usrtxt)
    
    except Exception as e:
        await message.reply(f"**Error:** {str(e)}")
    
    finally:
        # Remove chat from active tagging list
        if chat_id in spam_chats:
            spam_chats.remove(chat_id)

@Client.on_message(filters.command("cancel", prefixes=HARDCODED_PREFIXES) & filters.me) 
@retry()
async def cancel_spam(client, message):
    if not message.chat.id in spam_chats:
        return await message.edit("**Looks like there is no tagall here.**")
    else:
        try:
            spam_chats.remove(message.chat.id)
        except:
            pass
        return await message.edit("**Dismissing Mention.**")
