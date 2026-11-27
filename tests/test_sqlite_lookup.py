"""Tests for path lookups in SQLiteTrie."""

import os

import pytest

from sqltrie import SQLiteTrie


@pytest.fixture(params=[1, 6])
def wide_trie(request):
    trie = SQLiteTrie()
    prefix = ("parent",) * request.param
    trie[prefix] = b"prefix"
    parent = trie._get_node(prefix)["id"]
    # Bulk insertion keeps fixture construction independent of lookup performance.
    trie._conn.executemany(
        "INSERT INTO nodes(pid, name, has_value, value) VALUES (?, ?, 1, ?)",
        [(parent, f"file_{index:06}", b"value") for index in range(10_000)],
    )
    trie.commit()
    try:
        yield trie, prefix
    finally:
        trie.close()


def test_lookup_does_not_scan_siblings(wide_trie):
    trie, prefix = wide_trie
    progress_calls = 0

    def progress():
        nonlocal progress_calls
        progress_calls += 1
        return 0

    # Count VM instructions rather than wall time or SQLite-specific plan text.
    # An indexed path lookup needs far fewer than 20,000 instructions; a scan
    # of the 10,000 unrelated siblings exceeds this generous budget.
    trie._conn.set_progress_handler(progress, 1_000)
    try:
        assert trie[(*prefix, "file_009999")] == b"value"
    finally:
        trie._conn.set_progress_handler(None, 0)
    assert progress_calls < 20


def test_lookup_does_not_commit(tmp_path):
    trie = SQLiteTrie.open(os.fspath(tmp_path / "db"))
    trie[("foo",)] = b"1"
    trie.commit()

    trie[("bar",)] = b"2"
    assert trie[("foo",)] == b"1"
    trie.rollback()

    assert not trie.has_node(("bar",))
    trie.close()


def test_lookup_reads_one_snapshot(tmp_path):
    path = os.fspath(tmp_path / "db")
    trie = SQLiteTrie.open(path)
    trie[("foo",)] = b"old"
    trie[("foo", "bar")] = b"old"
    trie.commit()

    writer = SQLiteTrie.open(path)
    selects = 0

    def commit_between_steps(statement):
        nonlocal selects
        if not statement.lstrip().startswith("SELECT"):
            return
        selects += 1
        # The lookup has read ("foo",) and is about to read ("foo", "bar").
        if selects == 2:
            writer[("foo",)] = b"new"
            writer[("foo", "bar")] = b"new"
            writer.commit()

    trie._conn.set_trace_callback(commit_between_steps)
    try:
        values = [value for _, value in trie.prefixes(("foo", "bar"))]
    finally:
        trie._conn.set_trace_callback(None)

    assert values == [b"old", b"old"]
    assert [value for _, value in trie.prefixes(("foo", "bar"))] == [b"new", b"new"]
    writer.close()
    trie.close()
