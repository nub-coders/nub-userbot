"""Tests for config._MemoryCollection — the in-memory Mongo shim used when
MONGO_URI is unset. Covers each update operator plus find/find_one/insert."""
from config import _MemoryCollection


def test_insert_and_find_one():
    c = _MemoryCollection()
    c.insert_one({"user_id": 1, "name": "a"})
    assert c.find_one({"user_id": 1})["name"] == "a"
    assert c.find_one({"user_id": 999}) is None
    assert c.find_one() is None


def test_find_one_returns_copy_not_reference():
    c = _MemoryCollection()
    c.insert_one({"user_id": 1, "list": [1]})
    got = c.find_one({"user_id": 1})
    got["list"].append(2)
    # Mutating the returned doc must not corrupt the stored one.
    assert c.find_one({"user_id": 1})["list"] == [1]


def test_update_set_and_unset():
    c = _MemoryCollection()
    c.insert_one({"user_id": 1, "x": 1})
    c.update_one({"user_id": 1}, {"$set": {"y": 2}})
    assert c.find_one({"user_id": 1}) == {"user_id": 1, "x": 1, "y": 2}
    c.update_one({"user_id": 1}, {"$unset": {"x": ""}})
    assert "x" not in c.find_one({"user_id": 1})


def test_update_push_and_pull():
    c = _MemoryCollection()
    c.insert_one({"user_id": 1})
    c.update_one({"user_id": 1}, {"$push": {"items": "a"}})
    c.update_one({"user_id": 1}, {"$push": {"items": "b"}})
    assert c.find_one({"user_id": 1})["items"] == ["a", "b"]
    c.update_one({"user_id": 1}, {"$pull": {"items": "a"}})
    assert c.find_one({"user_id": 1})["items"] == ["b"]


def test_update_addtoset_dedupes():
    c = _MemoryCollection()
    c.insert_one({"user_id": 1})
    c.update_one({"user_id": 1}, {"$addToSet": {"s": 5}})
    c.update_one({"user_id": 1}, {"$addToSet": {"s": 5}})
    assert c.find_one({"user_id": 1})["s"] == [5]


def test_update_inc_from_missing_and_existing():
    c = _MemoryCollection()
    c.insert_one({"user_id": 1})
    c.update_one({"user_id": 1}, {"$inc": {"n": 1}})
    c.update_one({"user_id": 1}, {"$inc": {"n": 4}})
    assert c.find_one({"user_id": 1})["n"] == 5


def test_update_upsert_creates_doc():
    c = _MemoryCollection()
    res = c.update_one({"user_id": 7}, {"$set": {"x": 1}}, upsert=True)
    assert c.find_one({"user_id": 7}) == {"user_id": 7, "x": 1}
    assert res.matched_count == 1


def test_update_no_upsert_on_missing_is_noop():
    c = _MemoryCollection()
    res = c.update_one({"user_id": 7}, {"$set": {"x": 1}}, upsert=False)
    assert c.find_one({"user_id": 7}) is None
    assert res.matched_count == 0


def test_find_all_and_filtered():
    c = _MemoryCollection()
    c.insert_one({"user_id": 1, "tag": "x"})
    c.insert_one({"user_id": 2, "tag": "y"})
    assert len(c.find()) == 2
    assert [d["user_id"] for d in c.find({"tag": "y"})] == [2]
