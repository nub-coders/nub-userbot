# Contributing to nub-userbot

Thanks for your interest! nub-userbot is a feature-rich Telegram userbot built with Pyrogram (Kurigram), offering automation and utility features for power users.

## Quick Start

### Prerequisites

- Python 3.13
- FFmpeg and libmagic installed on your system
- Telegram API credentials (API_ID, API_HASH)
- A Pyrogram session string

### Local Setup

```bash
# Clone the repo
git clone https://github.com/nub-coders/nub-userbot.git
cd nub-userbot

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials (see config.py for all variables)

# Run the userbot
python3 main.py
```

## Project Structure

```
├── main.py              Entry point
├── config.py            Environment configuration
├── plugin_loader.py     Loads community plugins from an external dir
├── userbot/             Userbot command modules
│   ├── account.py       Account management
│   ├── admin.py         Admin tools
│   ├── ai_agent.py      Agentic AI assistant (.ask)
│   ├── clone.py         Profile cloning
│   └── ...              (afk, eval, font, forward, etc.)
├── bot/                 Bot-mode features (inline, downloader)
├── utils/               Shared helpers
├── ruff.toml            Lint configuration
└── .env.example         Environment template
```

## Making Changes

1. **Fork and clone** your fork
2. **Create a feature branch** from `main`
3. **Run the linter locally** before pushing
4. **Keep commits focused** — one logical change per commit
5. **Open a PR** describing what changed and why

## Linting

This project has a lint gate that runs in CI:

```bash
# Run the linter (scoped gate — see ruff.toml)
ruff check .
```

It must pass before a PR can be merged.

## Code Style

- Python 3.13, formatted and linted with [ruff](https://docs.astral.sh/ruff/)
- Follow PEP 8 where practical
- Keep functions small and focused
- Match the existing patterns before introducing new ones
- Run `ruff check .` before committing

## Adding Plugins

nub-userbot supports loading community plugins from an external directory
without forking (see `plugin_loader.py`). This is the preferred way to add
custom commands — you don't need to modify the core repo.

## Pull Request Guidelines

- Describe what the PR does
- Link any related issues
- Ensure `ruff check .` passes
- Update README if you added commands or changed setup

## Need Help?

- Join the Telegram group: https://t.me/nub_coder_s
- Open an issue with your question
- Check existing issues and PRs first

## License

By contributing, you agree your contributions will be licensed under the same MIT License that covers this project.
