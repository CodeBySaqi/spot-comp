"""Kruskal's minimum spanning tree algorithm.

Classic ARIN-1108 graph algorithm: given an undirected weighted graph,
finds the set of edges of minimum total weight that connects every node.
Sorts all edges by weight and greedily takes each edge that joins two
different components, using the Union-Find from ``union_find.py`` to
test that in near-constant time. Runs in O(E log E).

Unlike Dijkstra, Kruskal handles negative edge weights fine — it never
relies on distances, only on the ordering of the weights. On a
disconnected graph it returns a minimum spanning *forest* instead.
"""

from typing import List, Tuple

from .union_find import UnionFind

# Edge: (node u, node v, weight). Nodes are ``0 .. n-1``.
Edge = Tuple[int, int, float]


def kruskal(n: int, edges: List[Edge]) -> Tuple[List[Edge], float]:
    """Return ``(mst_edges, total_weight)`` for the graph on ``n`` nodes.

    ``mst_edges`` are the chosen edges, in the order Kruskal picked
    them (non-decreasing weight, ties broken by endpoint). On a
    disconnected graph this is a minimum spanning forest: fewer than
    ``n - 1`` edges, one tree per connected component.

    Self-loops are ignored (they can never join two components).
    Raises ``ValueError`` for a negative ``n`` and ``IndexError`` for
    an endpoint outside ``0 .. n-1``.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    for u, v, _weight in edges:
        if not 0 <= u < n or not 0 <= v < n:
            raise IndexError(f"edge endpoint out of range: ({u}, {v})")

    uf = UnionFind(n)
    # Deterministic order: weight first, then endpoints, so equal-weight
    # runs always pick the same tree.
    ordered = sorted(edges, key=lambda e: (e[2], min(e[0], e[1]), max(e[0], e[1])))
    mst: List[Edge] = []
    total = 0.0
    for u, v, weight in ordered:
        if u == v:
            continue  # self-loop: joins nothing
        if uf.union(u, v):
            mst.append((u, v, weight))
            total += weight
            if len(mst) == n - 1:
                break
    return mst, total
