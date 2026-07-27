"""Load community plugins from an external directory without forking the repo.

Kurigram's built-in ``plugins=dict(root=...)`` only accepts a single root and
its ``root`` is used as ``root.replace(".", "/")`` — so a list of roots is not
supported (verified against kurigram 2.2.23's ``Client.load_plugins``). This
module reproduces exactly what that loader does for one extra directory: import
each ``*.py`` file, then ``add_handler`` for every decorated function found.
Importing alone does NOT register handlers — the ``@Client.on_message``
decorator only stashes ``.handlers`` on the function; the client must add them.

Each file is loaded in isolation: an import error or a bad handler in one
plugin is logged and skipped, never aborting startup.
"""
import importlib.util
import logging
from pathlib import Path

from pyrogram.handlers.handler import Handler

logger = logging.getLogger("plugins")


def load_extra_plugins(client, directory):
    """Import every ``*.py`` in ``directory`` and register its handlers on
    ``client``. Returns the list of successfully loaded module stems."""
    loaded = []
    d = Path(directory)
    if not d.is_dir():
        logger.info("[PLUGINS] No extra plugins dir at %s", directory)
        return loaded

    for path in sorted(d.rglob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"extra_plugins.{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logger.warning("[PLUGINS] Failed to import %s: %s", path.name, e)
            continue

        count = 0
        for name in vars(module):
            try:
                for handler, group in getattr(getattr(module, name), "handlers", []):
                    if isinstance(handler, Handler) and isinstance(group, int):
                        client.add_handler(handler, group)
                        count += 1
            except Exception as e:
                logger.warning("[PLUGINS] Bad handler '%s' in %s: %s", name, path.name, e)

        if count:
            loaded.append(path.stem)
            logger.info("[PLUGINS] Loaded %d handler(s) from %s", count, path.name)
        else:
            logger.warning("[PLUGINS] No handlers found in %s", path.name)

    return loaded
