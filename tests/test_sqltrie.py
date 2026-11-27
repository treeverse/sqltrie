"""Tests for `sqltrie` package."""

import os

import pytest

from sqltrie import UNCHANGED, Change, PyGTrie, ShortKeyError, SQLiteTrie, TrieNode


@pytest.mark.parametrize("cls", [SQLiteTrie, PyGTrie])
def test_trie(cls):
    trie = cls()

    trie[("foo",)] = b"foo-value"
    trie[("foo", "bar", "baz")] = b"baz-value"

    assert len(trie) == 2
    assert trie[("foo",)] == b"foo-value"
    with pytest.raises(ShortKeyError):
        trie[("foo", "bar")]  # pylint: disable=pointless-statement
    assert trie[("foo", "bar", "baz")] == b"baz-value"

    del trie[("foo",)]
    assert len(trie) == 1
    assert trie[("foo", "bar", "baz")] == b"baz-value"

    with pytest.raises(ShortKeyError):
        trie[("foo",)]  # pylint: disable=pointless-statement

    with pytest.raises(ShortKeyError):
        trie[("foo", "bar")]  # pylint: disable=pointless-statement

    with pytest.raises(KeyError):
        trie[("non-existent",)]  # pylint: disable=pointless-statement

    with pytest.raises(KeyError):
        trie[("foo", "non-existent")]  # pylint: disable=pointless-statement

    assert trie.longest_prefix(()) is None
    assert trie.longest_prefix(("non-existent",)) is None
    assert trie.longest_prefix(("foo",)) is None
    assert trie.longest_prefix(("foo", "non-existent")) is None
    assert trie.longest_prefix(("foo", "bar", "baz", "qux")) == (
        ("foo", "bar", "baz"),
        b"baz-value",
    )

    assert set(trie.items()) == {
        (("foo", "bar", "baz"), b"baz-value"),
    }
    assert set(trie.items(shallow=True)) == {
        (("foo", "bar", "baz"), b"baz-value"),
    }
    assert set(trie.items(("foo",))) == {
        (("foo", "bar", "baz"), b"baz-value"),
    }
    assert set(trie.items(("foo", "bar"))) == {
        (("foo", "bar", "baz"), b"baz-value"),
    }
    assert set(trie.items(("foo", "bar", "baz"))) == {
        (("foo", "bar", "baz"), b"baz-value"),
    }

    assert set(trie.view(("foo",)).items()) == {
        (("bar", "baz"), b"baz-value"),
    }
    assert set(trie.view(("foo", "bar", "baz")).items()) == {
        ((), b"baz-value"),
    }

    assert list(trie.ls(())) == [("foo",)]
    assert list(trie.ls(("foo",))) == [("foo", "bar")]
    assert list(trie.ls(("foo", "bar"))) == [("foo", "bar", "baz")]

    assert not list(trie.diff(("foo",), ("foo",)))
    assert list(trie.diff(("foo",), ("foo",), with_unchanged=True)) == [
        Change(
            typ=UNCHANGED,
            old=TrieNode(key=("bar", "baz"), value=b"baz-value"),
            new=TrieNode(key=("bar", "baz"), value=b"baz-value"),
        ),
    ]


@pytest.mark.parametrize("cls", [SQLiteTrie, PyGTrie])
def test_set_get(cls):
    trie = cls()

    trie[("foo", "bar")] = b"1"
    with pytest.raises(ShortKeyError):
        trie[()]  # pylint: disable=pointless-statement
    with pytest.raises(ShortKeyError):
        trie[("foo",)]  # pylint: disable=pointless-statement
    assert trie[("foo", "bar")] == b"1"

    trie[("foo",)] = b"2"
    with pytest.raises(ShortKeyError):
        trie[()]  # pylint: disable=pointless-statement
    assert trie[("foo",)] == b"2"
    assert trie[("foo", "bar")] == b"1"

    trie[("foo'bar",)] = b"2"
    assert trie[("foo'bar",)] == b"2"


@pytest.mark.parametrize("cls", [SQLiteTrie, PyGTrie])
@pytest.mark.parametrize("name", ["", "/", "foo/bar"])
def test_unusual_key_component(cls, name):
    trie = cls()

    trie[(name,)] = b"1"
    trie[("qux", name)] = b"2"
    trie[(name, "qux", "xyz")] = b"3"

    assert trie[(name,)] == b"1"
    assert trie[("qux", name)] == b"2"
    assert trie[(name, "qux", "xyz")] == b"3"
    assert trie.longest_prefix(()) is None
    assert trie.longest_prefix((name, "qux")) == ((name,), b"1")
    assert set(trie.items()) == {
        ((name,), b"1"),
        (("qux", name), b"2"),
        ((name, "qux", "xyz"), b"3"),
    }


@pytest.mark.parametrize("cls", [SQLiteTrie, PyGTrie])
def test_set_get_root(cls):
    trie = cls()

    trie[()] = b"root"
    assert trie[()] == b"root"
    del trie[()]
    with pytest.raises(KeyError):
        trie[()]  # pylint: disable=pointless-statement


@pytest.mark.parametrize("cls", [SQLiteTrie, PyGTrie])
def test_has_node(cls):
    trie = cls()

    trie[("foo", "bar")] = b"1"
    assert trie.has_node(())
    assert trie.has_node(("foo",))
    assert trie.has_node(("foo", "bar"))
    assert not trie.has_node(("qux",))
    assert not trie.has_node(("foo", "qux"))
    assert not trie.has_node(("foo", "bar", "qux"))
    assert not trie.has_node(("foo", "bar", "qux", "xyz"))


def test_open(tmp_path):
    path = os.fspath(tmp_path / "db")
    trie = SQLiteTrie.open(path)

    assert len(trie) == 0

    trie[("foo",)] = b"foo-value"
    trie[("foo", "bar", "baz")] = b"baz-value"

    trie.commit()

    assert trie._ids == {(): 1, ("foo",): 2, ("foo", "bar"): 3}
    assert trie._local.conn
    trie.close()
    assert not trie._ids
    assert not hasattr(trie._local, "conn")

    trie = SQLiteTrie.open(path)

    assert len(trie) == 2

    assert trie[("foo",)] == b"foo-value"
    assert trie[("foo", "bar", "baz")] == b"baz-value"

    assert not trie._ids
    assert trie._local.conn
    trie.close()
    assert not trie._ids
    assert not hasattr(trie._local, "conn")


@pytest.mark.parametrize("cls", [SQLiteTrie, PyGTrie])
def test_view(cls):
    trie = cls()

    view = trie.view(("a",))
    assert not list(view.items())

    view = trie.view(("a", "b"))
    assert not list(view.items())

    view = trie.view(("a", "b", "c"))
    assert not list(view.items())
