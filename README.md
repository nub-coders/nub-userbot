
# 🤖 Advanced Nub Userbot

A feature-rich Telegram userbot built with Pyrogram, offering a wide range of automation and utility features for power users.

## ✨ Features

### 🎵 Music & Entertainment
- **Voice Chat Music**: Play music in Telegram voice chats with queue support
- **YouTube Integration**: Search and play music from YouTube
- **Audio/Video Support**: Handle various media formats
- **Queue Management**: Add, skip, and manage music queues

### 📁 File Management
- **Auto-Download**: Automatically save media from specified channels
- **File Tools**: Upload, download, and manage files efficiently
- **Media Processing**: Generate thumbnails and process videos
- **Large File Support**: Handle files larger than Telegram's limits via external services

### 🛠️ Utility Tools
- **Stats Tracking**: Monitor chat statistics and user activity
- **Session Management**: View and manage active Telegram sessions
- **Ping/Uptime**: Check bot responsiveness and uptime
- **Info Commands**: Get detailed user and chat information

### 🎨 Customization
- **Font Styles**: Apply various text formatting styles
- **Sticker Tools**: Create and manage custom stickers
- **Profile Management**: Clone and revert user profiles
- **Custom Responses**: Set personalized auto-responses

### 🔧 Admin Tools
- **User Management**: Approve/disapprove users, manage whitelists
- **Spam Control**: Advanced spam detection and prevention
- **Raid Protection**: Automated raid response system
- **Message Management**: Bulk delete, purge, and moderate messages

### 🤖 AI Integration
- **Gemini AI**: Multiple AI commands for chat, reasoning, and code generation
- **Smart Responses**: AI-powered text completion and analysis
- **Content Generation**: Automated writing and summarization

### 📱 Communication
- **Auto-Reply**: Intelligent message handling in private chats
- **AFK System**: Away-from-keyboard status with custom messages
- **Broadcast**: Send messages to multiple chats simultaneously
- **Scheduled Messages**: Schedule messages for later delivery

## 🚀 Quick Setup

### Prerequisites
- Python 3.8+
- Telegram API credentials (API ID and Hash)
- Pyrogram session string
- MongoDB database (optional — falls back to in-memory storage if not set)

### Installation

1. **Get your Telegram API credentials:**
   - Visit [my.telegram.org](https://my.telegram.org)
   - Create a new application
   - Note down your `API_ID` and `API_HASH`

2. **Generate a session string:**
   - Use any session string generator for Pyrogram (kurigram)
   - Save the session string securely

3. **Configure the bot:**
   - Copy `.env.example` to `.env` and fill in your credentials
   - At minimum set `API_ID`, `API_HASH`, and `SESSION_STR`
   - Everything else is optional (see [Configuration](#️-configuration))

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the userbot:**
   ```bash
   python main.py
   ```
   - If `SESSION_STR` is not set, you will be prompted for a session string
   - The bot will start and load all plugins

### Run with Docker

```bash
docker compose up -d
```

## 🚢 Deploy

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/nub-coders/nub-userbot)

[![Deploy to Halvo](https://halvo.nubcoders.com/deploy/button.svg)](https://halvo.nubcoders.com/deploy?template=https://github.com/nub-coders/nub-userbot)

- A `Procfile` and `app.json` are included for easy deployment (see repository root).

## ⚙️ Configuration

All configuration is done through environment variables (or a `.env` file). See `.env.example` for the full list.

### Required
- `API_ID` / `API_HASH` — Telegram API credentials from [my.telegram.org](https://my.telegram.org)
- `SESSION_STR` — your Pyrogram session string

### Optional
- `BOT_TOKEN` — bot token from [@BotFather](https://t.me/BotFather), enables inline bot features
- `GEMINI_API_KEY` — Google Gemini API key from [aistudio.google.com](https://aistudio.google.com/app/apikey), enables AI features
- `YT_DLP_API_KEY` / `YT_DLP_BASE_URL` — YouTube download service configuration
- `MONGO_URI` / `DB_NAME` — MongoDB for persistent storage; leave `MONGO_URI` empty to use in-memory storage (data is lost on restart)
- `GROUP` / `CHANNEL` — your support group and updates channel usernames (without @)

## 📋 Commands Overview

### Basic Commands
- `.alive` - Check if userbot is running
- `.ping` - Test response time
- `.stats` - View comprehensive statistics
- `.info [user]` - Get user information

### Music Commands
- `.play <query>` - Play audio in voice chat
- `.vplay <query>` - Play video in voice chat
- `.skip` - Skip current track
- `.vc1 [title]` - Start voice chat
- `.vc0` - End voice chat

### File & Media
- `.qt` - Create quote stickers
- `.kang` - Add stickers to pack
- `.tiny` - Create tiny stickers
- `.mmf <text>` - Add text to images

### Utility Commands
- `.clone <user>` - Clone user profile
- `.revert` - Revert to original profile
- `.schedule <target> <time> <message>` - Schedule messages
- `.fonts` - Apply text formatting styles

### Admin Commands
- `.spam <count> <text>` - Send repeated messages
- `.tagall` - Mention all group members
- `.purge` - Delete message range
- `.power <type>` - Promote users with permissions

### AI Commands (Gemini, prefixed with `/`)
- `/chat <text>` - General AI conversation
- `/reason <text>` - Step-by-step problem solving
- `/code <request>` - Generate or fix code
- `/summarize <text>` - Summarize content
- `/translate <text>` - Translate languages
- `/write <topic>` - Generate written content
- `/analysis <text>` - In-depth analysis
- `/gemini_help` - List all AI commands

## ⭐ Telegram Premium Features

Some features rely on a **Telegram Premium** account on the userbot session. They will fail gracefully (raising `PremiumAccountRequired`) if the account is not Premium:

- **Custom Emoji Status**: `.setemoji <emoji>` sets an animated/custom emoji status on your account
- **Custom (Animated) Emojis**: sending premium custom emojis inside messages
- **Voice Chat Streaming**: streaming certain media in voice chats may require Premium depending on the chat

No extra configuration is needed — these activate automatically when the session account has Premium.

## 🛡️ Security Features

- **Admin Protection**: Prevents actions against configured admins
- **Rate Limiting**: Built-in flood protection
- **User Verification**: Whitelist/blacklist management
- **Session Security**: Monitor and manage active sessions

## 📝 Customization

### Adding Custom Commands
1. Create a new file in the `userbot/` or `bot/` directory
2. Import required modules and decorators
3. Use `@Client.on_message()` decorator with filters
4. Implement your command logic

### Custom Fonts and Styles
- Modify `fonts.py` to add new text formatting styles
- Use the `.fonts` command to apply custom formatting

### Auto-Response Settings
- Configure welcome messages for new users
- Set custom AFK messages and responses
- Personalize spam control settings

## 🔧 Troubleshooting

### Common Issues
- **Session Errors**: Regenerate session string if expired
- **Permission Errors**: Ensure proper admin rights in groups
- **Module Import Errors**: Check all dependencies are installed
- **Database Connection**: Verify `MONGO_URI`, or leave it empty to use in-memory storage

### Performance Tips
- Monitor memory usage for large file operations
- Use appropriate delays for spam prevention
- Regularly clean up temporary files

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details. Use responsibly and in accordance with Telegram's Terms of Service.

## ⚠️ Disclaimer

- This userbot is for educational and personal use only
- Users are responsible for complying with Telegram's ToS
- The developers are not responsible for any misuse
- Some features (custom emoji status, animated emojis) require a Telegram Premium account

## 🤝 Support

For issues and support:
- Check the troubleshooting section
- Review command documentation
- Ensure proper configuration

---

**Note**: This userbot includes advanced features that may require technical knowledge to configure and use effectively. Please read all documentation before deployment.
