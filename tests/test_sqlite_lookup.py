"""Regression tests for path lookups beneath a wide SQLite trie node."""

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
