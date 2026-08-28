"""Pluggable session storage.

There is exactly one collection in this project (``user_sessions``), a
document-per-``user_id`` store. MongoDB's own ``Collection`` already satisfies
the shape the code uses (``find_one``/``insert_one``/``update_one``/``find``
with ``$set``/``$unset``/``$push``/``$pull``/``$addToSet``/``$inc``), so the
"interface" here is just that duck type — no ABC, no Mongo wrapper. This module
provides the two pure-Python backends: in-memory (lost on restart) and SQLite
(persistent, stdlib only, no external DB), plus a thin proxy that reports writes
so caches elsewhere can drop what they are holding.
"""
import copy
import json
import logging
import os
import sqlite3
import threading

logger = logging.getLogger(__name__)


class _Result:
    """Mimics pymongo UpdateResult / InsertOneResult."""
    def __init__(self, matched=0, modified=0, inserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.inserted_id = inserted_id


def _resolve(doc, field, create=False):
    """Walk a dotted field path, returning the owning dict and the final key.

    Mongo reads ``a.b`` as a path into a nested document and every operator below
    accepts one. This used the dotted string as a literal key instead, so
    ``{"$inc": {f"users.{uid}": 1}}`` (userbot/antyspam.py) created a top-level
    ``"users.<uid>"`` entry that the matching read -- ``doc.get("users", {}).get(uid)``
    -- could never see. The per-sender antispam counters therefore read 0 forever
    on the memory and sqlite backends, so the auto-delete and auto-block
    thresholds never fired and the reset commands had nothing to reset, while the
    same code worked on mongo. Returns ``(None, key)`` when the path does not
    exist and ``create`` is false, so read-only operators can bail out.
    """
    parts = field.split(".")
    for part in parts[:-1]:
        child = doc.get(part)
        if not isinstance(child, dict):
            if not create:
                return None, parts[-1]
            child = {}
            doc[part] = child
        doc = child
    return doc, parts[-1]


def _apply_update(doc, update):
    """Apply Mongo-style update operators to ``doc`` in place."""
    for op, fields in update.items():
        if op == "$set":
            for f, v in fields.items():
                owner, key = _resolve(doc, f, create=True)
                owner[key] = v
        elif op == "$unset":
            for f in fields:
                owner, key = _resolve(doc, f)
                if owner is not None:
                    owner.pop(key, None)
        elif op == "$push":
            for f, v in fields.items():
                owner, key = _resolve(doc, f, create=True)
                owner.setdefault(key, []).append(v)
        elif op == "$pull":
            for f, v in fields.items():
                owner, key = _resolve(doc, f)
                lst = owner.get(key, []) if owner is not None else []
                if v in lst:
                    lst.remove(v)
        elif op == "$addToSet":
            for f, v in fields.items():
                owner, key = _resolve(doc, f, create=True)
                lst = owner.setdefault(key, [])
                if v not in lst:
                    lst.append(v)
        elif op == "$inc":
            for f, v in fields.items():
                owner, key = _resolve(doc, f, create=True)
                owner[key] = owner.get(key, 0) + v


class MemoryCollection:
    """In-memory Mongo-compatible collection. Works while the bot runs, lost on restart."""
    def __init__(self):
        self._docs = {}

    def find_one(self, filt=None, *a, **kw):
        if not filt:
            return None
        doc = self._docs.get(filt.get("user_id"))
        return copy.deepcopy(doc) if doc else None

    def insert_one(self, doc, *a, **kw):
        key = doc.get("user_id")
        self._docs[key] = copy.deepcopy(doc)
        return _Result(inserted_id=key)

    def update_one(self, filt, update, *a, upsert=False, **kw):
        key = filt.get("user_id")
        doc = self._docs.get(key)
        if doc is None:
            if not upsert:
                return _Result()
            doc = dict(filt)
            self._docs[key] = doc
        _apply_update(doc, update)
        return _Result(matched=1, modified=1)

    def find(self, filt=None, *a, **kw):
        if not filt:
            return list(self._docs.values())
        return [d for d in self._docs.values() if all(d.get(k) == v for k, v in filt.items())]


class SqliteCollection:
    """SQLite-backed, Mongo-compatible collection: one JSON doc per ``user_id``.

    Mirrors MemoryCollection semantics so it's a drop-in for ``user_sessions``.
    Documents must be JSON-serializable (the current feature set stores only
    ints/strings/lists, which are).
    """
    # ponytail: one shared connection behind a single lock. Fine for a
    # single-process userbot; move to a connection pool only if it ever runs
    # multi-process against the same file.
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions (user_id TEXT PRIMARY KEY, doc TEXT NOT NULL)"
        )
        self._conn.commit()
        self._drop_legacy_dotted_keys()

    def _drop_legacy_dotted_keys(self):
        """Remove top-level keys with a dot in the name, left by the bug ``_resolve`` fixed.

        Before that fix every ``{"$inc": {f"users.{uid}": 1}}`` wrote a literal
        ``"users.<uid>"`` key at the top of the document instead of incrementing
        ``users["<uid>"]``. Those keys are unreachable -- no read in the project
        looks for a dotted name -- so they sat there accumulating one dead entry
        per person who ever sent a DM, in a document sqlite rewrites whole on
        every incoming message.

        The values are dropped rather than folded into the nested counters. They
        count DMs received while the antispam thresholds were inert, so nobody was
        ever warned about them; merging them in would mean the next message from a
        long-standing correspondent could cross ``block_count`` and get them
        blocked with no warning, months after the messages it is counting. A
        counter that restarts is the same state the account has effectively been
        in all along.

        Only this backend needs it: Mongo always resolved dotted paths correctly,
        and MemoryCollection does not survive a restart.
        """
        with self._lock:
            rows = self._conn.execute("SELECT user_id, doc FROM sessions").fetchall()
            cleaned_docs = 0
            cleaned_keys = 0
            for user_id, raw in rows:
                try:
                    doc = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(doc, dict):
                    continue
                dotted = [k for k in doc if "." in k]
                if not dotted:
                    continue
                for key in dotted:
                    del doc[key]
                cleaned_docs += 1
                cleaned_keys += len(dotted)
                self._conn.execute(
                    "UPDATE sessions SET doc = ? WHERE user_id = ?",
                    (json.dumps(doc), user_id),
                )
            if cleaned_docs:
                self._conn.commit()
                logger.info(
                    "storage: dropped %s unreachable dotted key(s) from %s document(s)",
                    cleaned_keys, cleaned_docs,
                )

    def _get(self, key):
        row = self._conn.execute(
            "SELECT doc FROM sessions WHERE user_id = ?", (str(key),)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def _put(self, key, doc):
        self._conn.execute(
            "INSERT OR REPLACE INTO sessions (user_id, doc) VALUES (?, ?)",
            (str(key), json.dumps(doc)),
        )
        self._conn.commit()

    def find_one(self, filt=None, *a, **kw):
        if not filt:
            return None
        with self._lock:
            return self._get(filt.get("user_id"))

    def insert_one(self, doc, *a, **kw):
        key = doc.get("user_id")
        with self._lock:
            self._put(key, dict(doc))
        return _Result(inserted_id=key)

    def update_one(self, filt, update, *a, upsert=False, **kw):
        key = filt.get("user_id")
        with self._lock:
            doc = self._get(key)
            if doc is None:
                if not upsert:
                    return _Result()
                doc = dict(filt)
            _apply_update(doc, update)
            self._put(key, doc)
        return _Result(matched=1, modified=1)

    def find(self, filt=None, *a, **kw):
        with self._lock:
            rows = self._conn.execute("SELECT doc FROM sessions").fetchall()
        docs = [json.loads(r[0]) for r in rows]
        if not filt:
            return docs
        return [d for d in docs if all(d.get(k) == v for k, v in filt.items())]


class WriteObservedCollection:
    """Collection proxy that reports every write to registered observers.

    ``tools.py`` caches ``find_one`` results for half a minute, and invalidating
    that cache was left to each caller. Of the twenty-odd places that write to
    ``user_sessions``, exactly two remembered, so toggling a setting from the
    bot's settings menu could appear to do nothing for up to 30 seconds.
    Auditing every call site only fixes the ones that exist today; reporting
    from the single point all writes pass through fixes the ones added later
    too.

    Reads are forwarded untouched, so nothing here caches on its own.
    """

    # Everything pymongo offers that mutates. The pure-Python backends above
    # implement only a few of these; the rest are listed so that switching to
    # real Mongo, where they all exist, does not quietly reintroduce the bug.
    _WRITE_METHODS = frozenset({
        "insert_one", "insert_many",
        "update_one", "update_many", "replace_one",
        "delete_one", "delete_many",
        "find_one_and_update", "find_one_and_replace", "find_one_and_delete",
        "bulk_write",
    })

    def __init__(self, collection):
        self._collection = collection
        self._observers = []

    def on_write(self, callback):
        """Register ``callback(user_id)``, run after each write.

        ``user_id`` is ``None`` when the write's target could not be read off
        the call -- a bulk write, or a filter that does not name one -- which
        observers should treat as "assume everything changed".
        """
        self._observers.append(callback)

    def _notify(self, target):
        user_id = target.get("user_id") if isinstance(target, dict) else None
        if not isinstance(user_id, (int, str)):
            # Includes the {"user_id": {"$in": [...]}} shape: more than one
            # document, so no single id to hand over.
            user_id = None
        for callback in self._observers:
            try:
                callback(user_id)
            except Exception:
                # The write already succeeded. A broken observer must not turn
                # that into an exception the caller sees as a failed write.
                logger.exception("user_sessions write observer failed")

    def __getattr__(self, name):
        attr = getattr(self._collection, name)
        if name not in self._WRITE_METHODS:
            return attr

        def observed(*args, **kwargs):
            result = attr(*args, **kwargs)
            # First positional is the filter for updates/deletes and the
            # document for inserts; both carry user_id when they name one.
            target = args[0] if args else kwargs.get("filter") or kwargs.get("document")
            self._notify(target)
            return result

        observed.__name__ = name
        return observed


if __name__ == "__main__":
    # Self-check: both backends must behave identically for the operators the
    # bot actually uses.
    import tempfile

    def _exercise(c):
        c.insert_one({"user_id": 1, "n": 0, "tags": []})
        c.update_one({"user_id": 1}, {"$set": {"name": "x"}})
        c.update_one({"user_id": 1}, {"$inc": {"n": 5}})
        c.update_one({"user_id": 1}, {"$push": {"tags": "a"}})
        c.update_one({"user_id": 1}, {"$addToSet": {"tags": "a"}})   # no-op dup
        c.update_one({"user_id": 1}, {"$addToSet": {"tags": "b"}})
        c.update_one({"user_id": 1}, {"$pull": {"tags": "a"}})
        c.update_one({"user_id": 1}, {"$unset": {"name": ""}})
        c.update_one({"user_id": 2}, {"$set": {"y": 9}}, upsert=True)
        return c

    def _snap(c):
        return c.find_one({"user_id": 1}), sorted((c.find_one({"user_id": 2}) or {}).items())

    mem = _exercise(MemoryCollection())
    with tempfile.TemporaryDirectory() as d:
        sq = _exercise(SqliteCollection(os.path.join(d, "t.db")))
        assert _snap(mem) == _snap(sq), (_snap(mem), _snap(sq))
        assert mem.find_one({"user_id": 1})["tags"] == ["b"]
        assert mem.find_one({"user_id": 1}).get("name") is None
        assert mem.find_one({"user_id": 1})["n"] == 5
        assert mem.find_one({"user_id": 99}) is None
        assert len(mem.find()) == 2

    # The write proxy must forward reads and writes unchanged, and report the
    # affected user_id -- or None when the write does not name exactly one.
    seen = []
    obs = WriteObservedCollection(MemoryCollection())
    obs.on_write(seen.append)
    obs.insert_one({"user_id": 7, "n": 1})
    obs.update_one({"user_id": 7}, {"$inc": {"n": 1}})
    obs.update_one({"nothing": "here"}, {"$set": {"n": 0}})
    assert seen == [7, 7, None], seen
    assert obs.find_one({"user_id": 7})["n"] == 2, obs.find_one({"user_id": 7})
    assert len(obs.find()) == 1

    # Targets that name no single document report None. The backends above only
    # accept a scalar user_id, so check the extraction itself rather than
    # sending a filter they cannot answer.
    seen.clear()
    obs._notify({"user_id": {"$in": [7, 8]}})
    obs._notify([{"user_id": 7}, {"user_id": 8}])
    obs._notify(None)
    assert seen == [None, None, None], seen

    # A broken observer must not turn a successful write into an exception.
    obs.on_write(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    obs.update_one({"user_id": 7}, {"$set": {"n": 99}})
    assert obs.find_one({"user_id": 7})["n"] == 99

    # Opening a database written before _resolve existed must drop the literal
    # "users.<id>" keys that bug left behind, and touch nothing else -- including
    # a nested counter for the same sender, which is the live one.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "legacy.db")
        legacy = SqliteCollection(path)
        legacy.insert_one({
            "user_id": 1,
            "users.4242": 7,          # dead: written before the fix
            "users.99": 3,            # dead
            "users": {"4242": 2},     # live: written after it
            "block_count": 5,
            "white_listed": [11],
        })
        legacy._conn.close()

        reopened = SqliteCollection(path)
        doc = reopened.find_one({"user_id": 1})
        assert "users.4242" not in doc and "users.99" not in doc, doc
        assert doc["users"] == {"4242": 2}, doc
        assert doc["block_count"] == 5 and doc["white_listed"] == [11], doc
        # Idempotent, and a clean database is left exactly as it was.
        reopened._conn.close()
        assert SqliteCollection(path).find_one({"user_id": 1}) == doc

    print("storage self-check OK")
