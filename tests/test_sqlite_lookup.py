"""Regression tests for path lookups beneath a wide SQLite trie node."""

import pytest

from sqltrie import ShortKeyError, SQLiteTrie


@pytest.fixture(params=[1, 6])
def wide_trie(request):
    trie = SQLiteTrie()
    prefix = ("parent",) * request.param
    trie[()] = b"root"
    trie[prefix] = b"prefix"
    trie[(*prefix, "nested", "leaf")] = b"nested"
    parent = trie._get_node(prefix)["id"]
    # Bulk insertion keeps fixture construction independent of lookup performance.
    names = [f"file_{index:06}" for index in range(10_000)]
    names.extend(["quote'name", "unicode_ä"])
    trie._conn.executemany(
        "INSERT INTO nodes(pid, name, has_value, value) VALUES (?, ?, 1, ?)",
        [(parent, name, b"value") for name in names],
    )
    trie.commit()
    try:
        yield trie, prefix
    finally:
        trie.close()


@pytest.mark.parametrize("use_view", [False, True])
@pytest.mark.parametrize("name", ["file_000000", "file_009999", "missing"])
def test_lookup_does_not_scan_siblings(wide_trie, use_view, name):
    trie, prefix = wide_trie
    target = trie.view(prefix) if use_view else trie
    key = (name,) if use_view else (*prefix, name)
    progress_calls = 0

    def progress():
        nonlocal progress_calls
        progress_calls += 1
        return 0

    # Count VM instructions rather than wall time or SQLite-specific plan text.
    # An indexed path lookup needs far fewer than 20,000 instructions; a scan
    # of the 10,000 unrelated siblings exceeds this generous budget.
    target._conn.set_progress_handler(progress, 1_000)
    try:
        if name == "missing":
            with pytest.raises(KeyError):
                target[key]
        else:
            assert target[key] == b"value"
    finally:
        target._conn.set_progress_handler(None, 0)
    assert progress_calls < 20


def test_wide_lookup_values_prefixes_and_views(wide_trie):
    trie, prefix = wide_trie
    assert trie[()] == b"root"
    assert trie[prefix] == b"prefix"
    assert trie[(*prefix, "quote'name")] == b"value"
    assert trie[(*prefix, "unicode_ä")] == b"value"
    assert trie.longest_prefix((*prefix, "missing")) == (prefix, b"prefix")
    with pytest.raises(ShortKeyError):
        trie[(*prefix, "nested")]
    with pytest.raises(KeyError):
        trie[(*prefix, "missing", "leaf")]
    with pytest.raises(KeyError):
        trie[("missing", "leaf")]

    view = trie.view(prefix)
    assert view[()] == b"prefix"
    assert view[("quote'name",)] == b"value"
    assert view.view(("nested",))[("leaf",)] == b"nested"
    view[("created", "leaf")] = b"new"
    assert trie[(*prefix, "created", "leaf")] == b"new"
    del view[("created", "leaf")]
    with pytest.raises(ShortKeyError):
        trie[(*prefix, "created", "leaf")]
