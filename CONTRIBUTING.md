# Contributing

## Running the tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

Tests live in `tests/`. The suite covers the storage backends, session cache,
retry decorator, and plugin loader. CI runs on every push via GitHub Actions
(see `.github/workflows/test.yml`).

## Storage backends

The bot supports three session storage backends, selected via `STORAGE_BACKEND`:

| Value | Behavior |
|-------|----------|
| `mongo` | Persistent MongoDB (requires `MONGO_URI`). Falls back to memory on connection failure. |
| `sqlite` | Persistent SQLite, no external DB needed. Path: `SQLITE_PATH` (default `data/sessions.db`). |
| `memory` | In-memory only, lost on restart. Default when `MONGO_URI` is unset. |

See `storage.py` for the implementation.

## Writing a community plugin

Drop a `.py` file into `EXTRA_PLUGINS_DIR` (default `./plugins`) and restart.
The file just uses standard `@Client.on_message(...)` decorators — no extra API.
See `PLUGINS.md` for the full contract and examples.

## Code style

- Linting: `ruff check .` (scoped to defect-class rules — see `ruff.toml`).
- Logging: use `logging.getLogger(...)`, never `print()`.
- Exceptions: never bare `except:` — use `except Exception as e:` at minimum and log it.
- Storage writes: call `invalidate_session_cache(user_id)` after any `user_sessions.update_one`.
