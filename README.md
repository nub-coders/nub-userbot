
# 🤖 Advanced Nub Userbot

[![Tests](https://github.com/nub-coders/nub-userbot/actions/workflows/test.yml/badge.svg)](https://github.com/nub-coders/nub-userbot/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/github/license/nub-coders/nub-userbot)](LICENSE)
[![Stars](https://img.shields.io/github/stars/nub-coders/nub-userbot?style=flat)](https://github.com/nub-coders/nub-userbot/stargazers)
[![Python](https://img.shields.io/badge/python-3.13-blue)](https://www.python.org)

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
- **Message Management**: Bulk delete, purge, and moderate messages

### 🤖 AI Integration
- **AI Agent**: `.ask` runs a tool-use loop — the model can search the web, read files, and search the codebase before answering, and remembers the conversation per chat
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
- `AI_API_KEY` — API key for the AI gateway, enables the agentic `.ask` command and Word Grid vision
- `AGENT_MODEL` — model the agent uses (default `claude-opus-4-8`); set `AGENT_USE_CHEAPEST_MODEL=true` to auto-pick the cheapest model instead
- `AGENT_VISION_MODEL` — vision-capable model for image requests (default `claude-opus-4-8`)
- `AI_BASE_URL` — base URL of your Anthropic-compatible gateway; required alongside `AI_API_KEY`
- `AGENT_ALLOW_SHELL` — lets the agent run shell commands (default `false`; see the warning under AI Agent Commands)
- `AGENT_ALLOW_MODERATION` — lets the agent ban/kick/mute/promote members and delete or pin messages (default `false`; same warning)
- `AGENT_ALLOW_TELEGRAM_API` — lets the agent call *any* Telegram client method, not just moderation (default `false`; **supersedes** the moderation guards — see the warning under AI Agent Commands)
- `YTUBE_API_KEY` / `YTUBE_BASE_URL` — YouTube download service configuration
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

### AI Commands
- `.ask <question>` - Ask the agent; it can search the web, read files, search the codebase, inspect the current chat, and identify a member from a @handle, an ID, or a stylized display name before answering. Reply to a message to pass it along as context.
- `.askclear` - Forget the agent's conversation memory for this chat (`.askreset` also works)
- `.askmodel [refresh]` - Show the active model, how it was selected, its pricing, and whether the shell, moderation, and full-API tools are armed

> Requires `AI_API_KEY` and `AI_BASE_URL`. The agent's shell tool is **off by default** — `.ask` can embed text from other people's messages into the prompt, so enabling `AGENT_ALLOW_SHELL=true` turns that text into a command-injection path. Use `.eval` / `.sh` to run commands yourself instead.
>
> Moderation is off by default for the same reason. With `AGENT_ALLOW_MODERATION=true` the agent can ban, unban, kick, mute, unmute, promote, demote, and set admin titles, and delete or pin the replied-to message — so a message asking to be banned becomes an attack. Even armed, the tools work only in groups where the userbot already holds the matching admin right, never touch the chat owner or the userbot's own account, refuse to ban/kick/mute another admin, never grant `can_promote_members`, stop after 10 actions per `.ask`, and log every attempt as `[ask-moderation]`. Use `.ban` / `.mute` / `.promote` yourself if you would rather decide each one.
>
> `AGENT_ALLOW_TELEGRAM_API=true` goes further and lets the agent call *any* Telegram client method by name — the whole Pyrogram API, not just moderation. This **supersedes** the moderation guards rather than adding to them: a raw `ban_chat_member` call bypasses the owner/admin/self refusals and the 10-action cap, and it can act on **any chat the account is in**, not only the one `.ask` ran in. What it keeps is a per-run call budget, a result-size cap, an audit line (`[ask-api]`) per call, and a hard block on session-, login-, lifecycle-, raw-invoke-, and host-file methods. Treat this as equivalent to handing that person the account, and leave it off unless you mean to.

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
