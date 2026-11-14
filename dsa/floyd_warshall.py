"""Floyd-Warshall all-pairs shortest-path algorithm.

Classic ARIN-1108 graph algorithm: given a weighted directed graph,
finds the shortest distance between *every* pair of nodes at once,
plus the next-hop map needed to rebuild any shortest path. Runs in
O(V**3) — slower than running Dijkstra from each node on sparse
graphs, but it handles negative edge weights, which Dijkstra rejects
(see ``dijkstra.py``: "use Bellman-Ford instead"), and it is the
simplest correct route when all pairs are needed.
"""

import math
from typing import Dict, Hashable, List, Sequence, Tuple

Node = Hashable
# Adjacency list: node -> [(neighbour, weight), ...]
Graph = Dict[Node, Sequence[Tuple[Node, float]]]


def floyd_warshall(
    graph: Graph,
) -> Tuple[Dict[Node, Dict[Node, float]], Dict[Node, Dict[Node, Node]]]:
    """Return ``(distances, next_hop)`` for every pair of nodes.

    ``distances[u][v]`` is the shortest distance from ``u`` to ``v``,
    or ``math.inf`` when ``v`` is unreachable from ``u``; the diagonal
    is always 0. ``next_hop[u][v]`` is the first node after ``u`` on a
    shortest ``u`` -> ``v`` path (absent when ``u == v`` or ``v`` is
    unreachable from ``u``).

    Raises ``ValueError`` if the graph contains a negative-weight
    cycle — on such a cycle distances keep dropping forever, so no
    shortest path exists for the nodes on it.
    """
    # Every node named anywhere in the graph, keys and neighbours alike.
    nodes = set(graph)
    for neighbours in graph.values():
        for neighbour, _weight in neighbours:
            nodes.add(neighbour)

    distances: Dict[Node, Dict[Node, float]] = {
        u: {v: (0.0 if u == v else math.inf) for v in nodes} for u in nodes
    }
    next_hop: Dict[Node, Dict[Node, Node]] = {u: {} for u in nodes}

    for u, neighbours in graph.items():
        for v, weight in neighbours:
            if weight < distances[u][v]:
                distances[u][v] = float(weight)
                next_hop[u][v] = v

    # Try every node as an intermediate: any shortest path using
    # intermediates from a prefix of the nodes is settled after each
    # round, so after all rounds every shortest path is settled.
    for k in nodes:
        for u in nodes:
            if distances[u][k] == math.inf:
                continue
            for v in nodes:
                via_k = distances[u][k] + distances[k][v]
                if via_k < distances[u][v]:
                    distances[u][v] = via_k
                    next_hop[u][v] = next_hop[u][k]

    for u in nodes:
        if distances[u][u] < 0:
            raise ValueError(f"negative cycle reachable from {u!r}")

    return distances, next_hop


def shortest_path(graph: Graph, source: Node, target: Node) -> List[Node]:
    """Return the list of nodes on a shortest path ``source`` -> ``target``.

    Returns ``[]`` when ``target`` is unreachable from ``source``.

    Raises ``KeyError`` if ``source`` is not in the graph.
    """
    distances, next_hop = floyd_warshall(graph)
    if source not in distances:
        raise KeyError(f"source {source!r} not in graph")
    if distances[source].get(target, math.inf) == math.inf:
        return []
    path = [source]
    while path[-1] != target:
        path.append(next_hop[path[-1]][target])
    return path
