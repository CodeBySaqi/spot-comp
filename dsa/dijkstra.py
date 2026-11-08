"""Dijkstra's shortest-path algorithm.

Classic ARIN-1108 graph algorithm: given a weighted graph with
non-negative edge weights, finds the shortest distance from a source
node to every reachable node, plus the predecessor map needed to
rebuild any shortest path. Runs in O((V + E) log V) with a heap.
"""

import heapq
import math
from typing import Dict, Hashable, List, Sequence, Tuple

Node = Hashable
# Adjacency list: node -> [(neighbour, weight), ...]
Graph = Dict[Node, Sequence[Tuple[Node, float]]]


def dijkstra(graph: Graph, source: Node) -> Tuple[Dict[Node, float], Dict[Node, Node]]:
    """Return ``(distances, predecessors)`` from ``source``.

    ``distances`` maps every node reachable from ``source`` (plus
    ``source`` itself, at distance 0) to its shortest distance;
    unreachable nodes are absent. ``predecessors`` maps each reached
    node (except ``source``) to the previous node on a shortest path.

    Raises ``KeyError`` if ``source`` is not in the graph and
    ``ValueError`` on a negative edge weight (Dijkstra cannot handle
    those — use Bellman-Ford instead).
    """
    if source not in graph:
        raise KeyError(f"source {source!r} not in graph")

    distances: Dict[Node, float] = {source: 0.0}
    predecessors: Dict[Node, Node] = {}
    heap: List[Tuple[float, Node]] = [(0.0, source)]

    while heap:
        dist, node = heapq.heappop(heap)
        if dist > distances[node]:
            continue  # stale heap entry
        for neighbour, weight in graph.get(node, []):
            if weight < 0:
                raise ValueError(
                    f"negative edge weight {weight} on {node!r} -> {neighbour!r}"
                )
            new_dist = dist + weight
            if new_dist < distances.get(neighbour, math.inf):
                distances[neighbour] = new_dist
                predecessors[neighbour] = node
                heapq.heappush(heap, (new_dist, neighbour))

    return distances, predecessors


def shortest_path(graph: Graph, source: Node, target: Node) -> List[Node]:
    """Return the list of nodes on a shortest path ``source`` -> ``target``.

    Returns ``[]`` when ``target`` is unreachable from ``source``.
    """
    distances, predecessors = dijkstra(graph, source)
    if target not in distances:
        return []
    path = [target]
    while path[-1] != source:
        path.append(predecessors[path[-1]])
    path.reverse()
    return path
