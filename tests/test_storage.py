"""Tests for the Mongo-compatible session backends (storage.py). Every case runs
against both MemoryCollection and SqliteCollection so they stay drop-in
interchangeable. Covers each update operator plus find/find_one/insert."""
import os

import pytest

from storage import MemoryCollection, SqliteCollection


@pytest.fixture(params=["memory", "sqlite"])
def c(request, tmp_path):
    if request.param == "memory":
        return MemoryCollection()
    return SqliteCollection(os.path.join(tmp_path, "sessions.db"))


def test_insert_and_find_one(c):
    c.insert_one({"user_id": 1, "name": "a"})
    assert c.find_one({"user_id": 1})["name"] == "a"
    assert c.find_one({"user_id": 999}) is None
    assert c.find_one() is None


def test_find_one_returns_copy_not_reference(c):
    c.insert_one({"user_id": 1, "list": [1]})
    got = c.find_one({"user_id": 1})
    got["list"].append(2)
    # Mutating the returned doc must not corrupt the stored one.
    assert c.find_one({"user_id": 1})["list"] == [1]


def test_update_set_and_unset(c):
    c.insert_one({"user_id": 1, "x": 1})
    c.update_one({"user_id": 1}, {"$set": {"y": 2}})
    assert c.find_one({"user_id": 1}) == {"user_id": 1, "x": 1, "y": 2}
    c.update_one({"user_id": 1}, {"$unset": {"x": ""}})
    assert "x" not in c.find_one({"user_id": 1})


def test_update_push_and_pull(c):
    c.insert_one({"user_id": 1})
    c.update_one({"user_id": 1}, {"$push": {"items": "a"}})
    c.update_one({"user_id": 1}, {"$push": {"items": "b"}})
    assert c.find_one({"user_id": 1})["items"] == ["a", "b"]
    c.update_one({"user_id": 1}, {"$pull": {"items": "a"}})
    assert c.find_one({"user_id": 1})["items"] == ["b"]


def test_update_addtoset_dedupes(c):
    c.insert_one({"user_id": 1})
    c.update_one({"user_id": 1}, {"$addToSet": {"s": 5}})
    c.update_one({"user_id": 1}, {"$addToSet": {"s": 5}})
    assert c.find_one({"user_id": 1})["s"] == [5]


def test_update_inc_from_missing_and_existing(c):
    c.insert_one({"user_id": 1})
    c.update_one({"user_id": 1}, {"$inc": {"n": 1}})
    c.update_one({"user_id": 1}, {"$inc": {"n": 4}})
    assert c.find_one({"user_id": 1})["n"] == 5


def test_update_upsert_creates_doc(c):
    res = c.update_one({"user_id": 7}, {"$set": {"x": 1}}, upsert=True)
    assert c.find_one({"user_id": 7}) == {"user_id": 7, "x": 1}
    assert res.matched_count == 1


def test_update_no_upsert_on_missing_is_noop(c):
    res = c.update_one({"user_id": 7}, {"$set": {"x": 1}}, upsert=False)
    assert c.find_one({"user_id": 7}) is None
    assert res.matched_count == 0


def test_find_all_and_filtered(c):
    c.insert_one({"user_id": 1, "tag": "x"})
    c.insert_one({"user_id": 2, "tag": "y"})
    assert len(c.find()) == 2
    assert [d["user_id"] for d in c.find({"tag": "y"})] == [2]


def test_sqlite_persists_across_reopen(tmp_path):
    path = os.path.join(tmp_path, "sessions.db")
    SqliteCollection(path).insert_one({"user_id": 1, "name": "persisted"})
    # A fresh handle to the same file must see the earlier write.
    assert SqliteCollection(path).find_one({"user_id": 1})["name"] == "persisted"
