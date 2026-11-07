import pytest

from dsa.union_find import UnionFind


def test_fresh_elements_are_singletons():
    uf = UnionFind(5)
    assert uf.num_components == 5
    assert all(uf.component_size(i) == 1 for i in range(5))
    assert not any(uf.connected(i, j) for i in range(5) for j in range(i + 1, 5))


def test_union_merges_and_reports():
    uf = UnionFind(4)
    assert uf.union(0, 1) is True
    assert uf.union(0, 1) is False  # already merged: no-op
    assert uf.connected(0, 1)
    assert uf.num_components == 3


def test_transitive_connectivity():
    uf = UnionFind(4)
    uf.union(0, 1)
    uf.union(1, 2)
    assert uf.connected(0, 2)
    assert uf.component_size(0) == 3
    assert uf.num_components == 2


def test_find_returns_stable_root():
    uf = UnionFind(6)
    uf.union(0, 1)
    uf.union(2, 3)
    uf.union(0, 2)
    roots = {uf.find(i) for i in (0, 1, 2, 3)}
    assert len(roots) == 1
    assert uf.component_size(5) == 1  # untouched element


def test_path_compression_flattens_long_chain():
    n = 1000
    uf = UnionFind(n)
    for i in range(n - 1):
        uf.union(i, i + 1)
    uf.find(0)  # trigger compression
    # after compression every node points straight at the root
    root = uf.find(n - 1)
    assert all(uf._parent[i] == root for i in range(n))


def test_union_by_rank_keeps_tree_shallow():
    n = 1024
    uf = UnionFind(n)
    for i in range(0, n, 2):
        uf.union(i, i + 1)
    for i in range(0, n, 4):
        uf.union(i, i + 2)
    uf.find(0)
    depth = 0
    x = 0
    while uf._parent[x] != x:
        x = uf._parent[x]
        depth += 1
    assert depth <= 4  # log2(1024) = 10 would be naive; rank keeps it tiny


def test_component_size_tracks_growth():
    uf = UnionFind(5)
    uf.union(0, 1)
    uf.union(2, 3)
    assert uf.component_size(0) == 2
    assert uf.component_size(3) == 2
    uf.union(0, 2)
    assert uf.component_size(1) == 4
    assert uf.num_components == 2


def test_self_union_is_noop():
    uf = UnionFind(3)
    assert uf.union(1, 1) is False
    assert uf.num_components == 3


def test_len_and_empty():
    assert len(UnionFind(7)) == 7
    assert UnionFind(0).num_components == 0


def test_out_of_range_raises():
    uf = UnionFind(3)
    with pytest.raises(IndexError):
        uf.find(3)
    with pytest.raises(IndexError):
        uf.find(-1)
    with pytest.raises(IndexError):
        uf.union(0, 99)
    with pytest.raises(IndexError):
        uf.connected(-2, 0)


def test_negative_n_rejected():
    with pytest.raises(ValueError):
        UnionFind(-1)


def test_kruskal_style_cycle_detection():
    # edges of a triangle + tail: only the closing edge forms a cycle
    uf = UnionFind(4)
    edges = [(0, 1), (1, 2), (2, 0), (2, 3)]
    cyclic = [not uf.union(a, b) for a, b in edges]
    assert cyclic == [False, False, True, False]
    assert uf.num_components == 1


def test_large_random_unions_stay_consistent():
    import random

    rng = random.Random(42)
    n = 500
    uf = UnionFind(n)
    parent = list(range(n))

    def ref_find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for _ in range(2000):
        a, b = rng.randrange(n), rng.randrange(n)
        merged = uf.union(a, b)
        ra, rb = ref_find(a), ref_find(b)
        assert merged == (ra != rb)
        if ra != rb:
            parent[rb] = ra
        assert uf.connected(a, b) == (ref_find(a) == ref_find(b))
