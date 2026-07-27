# Changelog

All notable changes to this project are documented here. Going forward, tag
releases on GitHub (`vX.Y.Z`) and add a matching section below.

## [Unreleased]

### Added
- Pluggable session storage via `STORAGE_BACKEND=mongo|sqlite|memory`, with a
  new stdlib-only SQLite backend for persistence without MongoDB
  (`SQLITE_PATH`, default `data/sessions.db`). See `storage.py`.
- External community plugin loading: drop `*.py` files in `EXTRA_PLUGINS_DIR`
  (default `./plugins`) and they load at startup. `.plugins` lists what loaded.
  See `PLUGINS.md`.
- `.update` command: `git pull`, reinstall dependencies only if
  `requirements.txt` changed, then restart via `os.execv`.
- Test suite (pytest + pytest-asyncio) and GitHub Actions CI with a scoped
  ruff gate. Storage tests run against both memory and SQLite backends.
- `CONTRIBUTING.md` and this changelog.

### Changed
- Split the `userbot/userbot.py` god-file (1,384 → 366 lines): help moved to
  `userbot/help.py`, ban/unban to `userbot/moderation.py`; dead code removed.
- Hygiene pass: replaced bare `except:` blocks with logged handlers, swapped
  stray `print()` for `logging`, pinned dependency versions.

### Fixed
- `welcome.py` called `unset_user_data`, which was never exported by `tools`
  (latent `NameError`) — added it to `tools.py`.
- `unban_all_users` called `delete_if_self`, defined nowhere in the repo
  (latent `NameError`) — added it to `tools.py`.
