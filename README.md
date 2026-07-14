
# 🤖 Advanced Pyrogram Userbot

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
- **DeepSeek AI**: Multiple AI commands for chat, reasoning, code generation
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
- MongoDB database
- Pyrogram session string

### Installation

1. **Get your Telegram API credentials:**
   - Visit [my.telegram.org](https://my.telegram.org)
   - Create a new application
   - Note down your `API_ID` and `API_HASH`

2. **Generate a session string:**
   - Use any session string generator for Pyrogram
   - Save the session string securely

3. **Configure the bot:**
   - Update `config.py` with your credentials
   - Set up MongoDB connection string
   - Configure admin settings in `admin.txt`

4. **Run the userbot:**
   ```bash
   python main.py
   ```
   - Enter your session string when prompted
   - The bot will start and load all plugins

## 🚢 Deploy

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/nub-coders/nub-userbot)

[![Deploy to Deplox](https://deplox.nubcoders.com/deploy/button.svg)](https://app.nubcoders.com/deploy?template=https://github.com/nub-coders/nub-userbot)

- A `Procfile` and `app.json` are included for easy deployment (see repository root).

## ⚙️ Configuration

### Essential Settings
- **API Credentials**: Set your `API_ID` and `API_HASH` in `config.py`
- **MongoDB**: Configure your database connection
- **Admin Access**: Add admin user IDs to `admin.txt`

### Optional Features
- **Premium Features**: Configure premium user management
- **AI Integration**: Set up DeepSeek API key for AI features
- **Custom Responses**: Personalize auto-reply messages

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
- `/chat <text>` - General AI conversation
- `/code <request>` - Generate code with AI
- `/summarize <text>` - Summarize content
- `/translate <text>` - Translate languages

## 🛡️ Security Features

- **Admin Protection**: Prevents actions against configured admins
- **Rate Limiting**: Built-in flood protection
- **User Verification**: Whitelist/blacklist management
- **Session Security**: Monitor and manage active sessions

## 📝 Customization

### Adding Custom Commands
1. Create a new file in the `plugins/` directory
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
- **Database Connection**: Verify MongoDB connection string

### Performance Tips
- Monitor memory usage for large file operations
- Use appropriate delays for spam prevention
- Regularly clean up temporary files

## 📄 License

This project is provided as-is for educational purposes. Use responsibly and in accordance with Telegram's Terms of Service.

## ⚠️ Disclaimer

- This userbot is for educational and personal use only
- Users are responsible for complying with Telegram's ToS
- The developers are not responsible for any misuse
- Some features may require premium Telegram accounts

## 🤝 Support

For issues and support:
- Check the troubleshooting section
- Review command documentation
- Ensure proper configuration

---

**Note**: This userbot includes advanced features that may require technical knowledge to configure and use effectively. Please read all documentation before deployment.
