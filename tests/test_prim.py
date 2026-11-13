import random

import pytest

from dsa.kruskal import kruskal
from dsa.prim import prim
from dsa.union_find import UnionFind


def total_weight(edges):
    return sum(w for _u, _v, w in edges)


def test_classic_four_node_graph():
    edges = [(0, 1, 1), (1, 2, 2), (2, 3, 3), (0, 3, 10), (0, 2, 5)]
    mst, total = prim(4, edges)
    assert total == 6
    assert {(min(u, v), max(u, v)) for u, v, _w in mst} == {(0, 1), (1, 2), (2, 3)}


def test_single_node_no_edges():
    assert prim(1, []) == ([], 0.0)


def test_empty_graph():
    assert prim(0, []) == ([], 0.0)


def test_disconnected_graph_returns_forest():
    # two separate pairs: one tree per component, no edge between them
    edges = [(0, 1, 4), (2, 3, 7), (0, 1, 9)]
    mst, total = prim(4, edges)
    assert total == 11
    assert len(mst) == 2
    assert {(min(u, v), max(u, v)) for u, v, _w in mst} == {(0, 1), (2, 3)}


def test_heaviest_edge_of_cycle_is_dropped():
    # triangle: the 100-weight edge closes the cycle, so it stays out
    edges = [(0, 1, 1), (1, 2, 1), (0, 2, 100)]
    mst, total = prim(3, edges)
    assert total == 2
    assert len(mst) == 2
    assert all(w != 100 for _u, _v, w in mst)


def test_equal_weights_are_deterministic():
    # a square with all weights 1: any 3 edges form an MST, but the
    # run must pick the same 3 every time
    edges = [(0, 1, 1), (1, 2, 1), (2, 3, 1), (3, 0, 1), (0, 2, 1)]
    first, _ = prim(4, edges)
    second, _ = prim(4, edges)
    assert first == second
    assert len(first) == 3
    assert total_weight(first) == 3


def test_negative_weights_allowed():
    # unlike Dijkstra, Prim only compares weights, so negatives are fine
    edges = [(0, 1, -5), (1, 2, 2), (0, 2, 3)]
    mst, total = prim(3, edges)
    assert total == -3
    assert (0, 1, -5) in mst


def test_self_loop_ignored():
    edges = [(0, 0, 1), (0, 1, 2), (1, 2, 3)]
    mst, total = prim(3, edges)
    assert total == 5
    assert all(u != v for u, v, _w in mst)


def test_parallel_edges_keep_cheapest():
    edges = [(0, 1, 10), (0, 1, 4), (0, 1, 7), (1, 2, 1)]
    mst, total = prim(3, edges)
    assert total == 5
    assert (0, 1, 4) in mst


def test_out_of_range_raises():
    with pytest.raises(IndexError):
        prim(3, [(0, 3, 1)])
    with pytest.raises(IndexError):
        prim(3, [(-1, 0, 1)])


def test_negative_n_rejected():
    with pytest.raises(ValueError):
        prim(-1, [])


def test_matches_kruskal_on_random_small_graphs():
    # Prim and Kruskal must agree on the MST total for every graph,
    # including disconnected ones and negative weights.
    rng = random.Random(7)
    for _ in range(30):
        n = rng.randint(2, 6)
        edges = []
        for u in range(n):
            for v in range(u + 1, n):
                if rng.random() < 0.7:
                    edges.append((u, v, rng.randint(-3, 9)))
        _mst, prim_total = prim(n, edges)
        _kmst, kruskal_total = kruskal(n, edges)
        assert prim_total == kruskal_total


def test_large_graph_is_spanning_tree():
    rng = random.Random(99)
    n = 200
    edges = [(i, i + 1, rng.randint(1, 50)) for i in range(n - 1)]
    edges += [
        (rng.randrange(n), rng.randrange(n), rng.randint(1, 50))
        for _ in range(800)
    ]
    edges = [(u, v, w) for u, v, w in edges if u != v]
    mst, total = prim(n, edges)
    assert len(mst) == n - 1
    assert total == total_weight(mst)
    uf = UnionFind(n)
    for u, v, _w in mst:
        assert uf.union(u, v)  # no cycles
    assert uf.num_components == 1
    # Same total as Kruskal on the same graph.
    _kmst, kruskal_total = kruskal(n, edges)
    assert total == kruskal_total
