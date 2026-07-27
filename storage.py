"""Pluggable session storage.

There is exactly one collection in this project (``user_sessions``), a
document-per-``user_id`` store. MongoDB's own ``Collection`` already satisfies
the shape the code uses (``find_one``/``insert_one``/``update_one``/``find``
with ``$set``/``$unset``/``$push``/``$pull``/``$addToSet``/``$inc``), so the
"interface" here is just that duck type — no ABC, no Mongo wrapper. This module
provides the two pure-Python backends: in-memory (lost on restart) and SQLite
(persistent, stdlib only, no external DB).
"""
import copy
import json
import os
import sqlite3
import threading


class _Result:
    """Mimics pymongo UpdateResult / InsertOneResult."""
    def __init__(self, matched=0, modified=0, inserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.inserted_id = inserted_id


def _apply_update(doc, update):
    """Apply Mongo-style update operators to ``doc`` in place."""
    for op, fields in update.items():
        if op == "$set":
            doc.update(fields)
        elif op == "$unset":
            for f in fields:
                doc.pop(f, None)
        elif op == "$push":
            for f, v in fields.items():
                doc.setdefault(f, []).append(v)
        elif op == "$pull":
            for f, v in fields.items():
                lst = doc.get(f, [])
                if v in lst:
                    lst.remove(v)
        elif op == "$addToSet":
            for f, v in fields.items():
                lst = doc.setdefault(f, [])
                if v not in lst:
                    lst.append(v)
        elif op == "$inc":
            for f, v in fields.items():
                doc[f] = doc.get(f, 0) + v


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
    print("storage self-check OK")
