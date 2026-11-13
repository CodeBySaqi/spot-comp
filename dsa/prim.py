"""Prim's minimum spanning tree algorithm.

Classic ARIN-1108 graph algorithm: given an undirected weighted graph,
finds the set of edges of minimum total weight that connects every node.
Grows one tree at a time from a starting node, repeatedly adding the
cheapest edge that joins the tree to a node outside it, using a heap
to pick that edge in O(log E). Runs in O(E log V).

The natural companion to Kruskal's algorithm in ``kruskal.py``: both
take the same ``(n, edges)`` input and return the same
``(mst_edges, total_weight)`` shape, and on any graph the two totals
agree — a useful cross-check. Unlike Dijkstra, Prim handles negative
edge weights fine, since it only ever compares weights, never sums
distances. On a disconnected graph it returns a minimum spanning
*forest* instead, one tree per connected component.
"""

import heapq
from typing import Dict, List, Tuple

# Edge: (node u, node v, weight). Nodes are ``0 .. n-1``.
Edge = Tuple[int, int, float]


def prim(n: int, edges: List[Edge]) -> Tuple[List[Edge], float]:
    """Return ``(mst_edges, total_weight)`` for the graph on ``n`` nodes.

    ``mst_edges`` are the chosen edges, in the order Prim picked them.
    On a disconnected graph this is a minimum spanning forest: fewer
    than ``n - 1`` edges, one tree per connected component.

    Self-loops are ignored (they can never join the tree to a new
    node). Raises ``ValueError`` for a negative ``n`` and ``IndexError``
    for an endpoint outside ``0 .. n-1``.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    for u, v, _weight in edges:
        if not 0 <= u < n or not 0 <= v < n:
            raise IndexError(f"edge endpoint out of range: ({u}, {v})")

    # Adjacency list: node -> [(weight, neighbour), ...]
    adj: Dict[int, List[Tuple[float, int]]] = {i: [] for i in range(n)}
    for u, v, weight in edges:
        if u == v:
            continue  # self-loop: joins nothing
        adj[u].append((weight, v))
        adj[v].append((weight, u))

    visited = [False] * n
    mst: List[Edge] = []
    total = 0.0

    for start in range(n):
        if visited[start]:
            continue
        # Grow one tree from ``start``.
        visited[start] = True
        # Heap entries: (weight, low endpoint, high endpoint, node).
        # The endpoints order the heap deterministically on ties.
        heap: List[Tuple[float, int, int, int]] = []
        for weight, neighbour in adj[start]:
            heapq.heappush(
                heap, (weight, min(start, neighbour), max(start, neighbour), neighbour)
            )
        while heap:
            weight, u, v, node = heapq.heappop(heap)
            if visited[node]:
                continue  # edge to a node already in the tree
            visited[node] = True
            mst.append((u, v, weight))
            total += weight
            for next_weight, neighbour in adj[node]:
                if not visited[neighbour]:
                    heapq.heappush(
                        heap,
                        (
                            next_weight,
                            min(node, neighbour),
                            max(node, neighbour),
                            neighbour,
                        ),
                    )

    return mst, total
