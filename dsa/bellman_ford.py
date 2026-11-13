"""Bellman-Ford shortest-path algorithm.

Classic ARIN-1108 graph algorithm: given a weighted directed graph,
finds the shortest distance from a source node to every reachable
node, plus the predecessor map needed to rebuild any shortest path.
Runs in O(V * E) — slower than Dijkstra, but it handles negative edge
weights, which Dijkstra rejects (see ``dijkstra.py``: "use
Bellman-Ford instead"). It also detects negative cycles reachable
from the source, where no shortest path exists at all.
"""

import math
from typing import Dict, Hashable, List, Sequence, Tuple

Node = Hashable
# Adjacency list: node -> [(neighbour, weight), ...]
Graph = Dict[Node, Sequence[Tuple[Node, float]]]


def bellman_ford(graph: Graph, source: Node) -> Tuple[Dict[Node, float], Dict[Node, Node]]:
    """Return ``(distances, predecessors)`` from ``source``.

    ``distances`` maps every node reachable from ``source`` (plus
    ``source`` itself, at distance 0) to its shortest distance;
    unreachable nodes are absent. ``predecessors`` maps each reached
    node (except ``source``) to the previous node on a shortest path.

    Raises ``KeyError`` if ``source`` is not in the graph and
    ``ValueError`` if a negative-weight cycle is reachable from
    ``source`` — on such a cycle distances keep dropping forever, so
    no shortest path exists. A negative cycle unreachable from the
    source is ignored.
    """
    if source not in graph:
        raise KeyError(f"source {source!r} not in graph")

    # Every node named anywhere in the graph, keys and neighbours alike.
    nodes = set(graph)
    for neighbours in graph.values():
        for neighbour, _weight in neighbours:
            nodes.add(neighbour)

    distances: Dict[Node, float] = {source: 0.0}
    predecessors: Dict[Node, Node] = {}

    # Relax every edge |V| - 1 times: after k rounds, every shortest
    # path using at most k edges is settled.
    for _ in range(max(len(nodes) - 1, 0)):
        changed = False
        for node, neighbours in graph.items():
            if node not in distances:
                continue
            for neighbour, weight in neighbours:
                new_dist = distances[node] + weight
                if new_dist < distances.get(neighbour, math.inf):
                    distances[neighbour] = new_dist
                    predecessors[neighbour] = node
                    changed = True
        if not changed:
            break  # settled early: nothing left to relax

    # One more pass: any edge that still relaxes sits on (or leads
    # from) a negative cycle reachable from the source.
    for node, neighbours in graph.items():
        if node not in distances:
            continue
        for neighbour, weight in neighbours:
            if distances[node] + weight < distances.get(neighbour, math.inf):
                raise ValueError(
                    f"negative cycle reachable from {source!r} "
                    f"via {node!r} -> {neighbour!r}"
                )

    return distances, predecessors


def shortest_path(graph: Graph, source: Node, target: Node) -> List[Node]:
    """Return the list of nodes on a shortest path ``source`` -> ``target``.

    Returns ``[]`` when ``target`` is unreachable from ``source``.
    Raises ``ValueError`` if a negative cycle is reachable from
    ``source``.
    """
    distances, predecessors = bellman_ford(graph, source)
    if target not in distances:
        return []
    path = [target]
    while path[-1] != source:
        path.append(predecessors[path[-1]])
    path.reverse()
    return path
