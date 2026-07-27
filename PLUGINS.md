# Community Plugins

Drop a `.py` file into the plugins directory and restart — no repo fork needed.

## Where

Default: `./plugins/` (repo root). Override with the `EXTRA_PLUGINS_DIR`
environment variable (absolute path or relative to the working directory).

The directory is scanned recursively at startup, after the built-in `userbot/`
plugins load. Files whose names start with `_` are skipped.

## The contract

A plugin file is a normal Kurigram/Pyrogram smart-plugin module. It just
defines handlers with the usual decorators — there is **no** extra API to
implement:

```python
from pyrogram import Client, filters

@Client.on_message(filters.command("ping", prefixes=[".", "!"]) & filters.me)
async def ping(client, message):
    await message.edit_text("pong")
```

At startup the loader imports each file and registers every function decorated
with `@Client.on_message(...)` (or any other `@Client.on_*` handler). This is
the same mechanism Kurigram uses for the built-in `userbot/` directory —
importing a file is not enough on its own, so the loader wires the handlers in
for you.

Helpers from the userbot are importable in a plugin via `from tools import *`
and `from config import *`, exactly like the built-in modules.

## Isolation

Each file loads independently: an import error or a malformed handler in one
plugin is logged and skipped — it will not stop the userbot from starting or
prevent other plugins from loading.

## Inspecting

`.plugins` lists what loaded from `EXTRA_PLUGINS_DIR`.

## Not yet supported (v2)

- `.installplugin <url>` — installing from a URL without a restart.
- Per-plugin namespace isolation beyond load-failure containment.

Both defer real complexity (safe dynamic re-import, fetching arbitrary code off
the internet) and will land only if v1 gets adopted.
