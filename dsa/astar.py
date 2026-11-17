"""A* search.

Classic ARIN-1108 graph algorithm: like Dijkstra's, but guided by a
heuristic — an estimate of the remaining cost from a node to the
target. With an admissible heuristic (one that never overestimates),
A* still finds a shortest path, and usually expands far fewer nodes
than Dijkstra's because the search is aimed at the target instead of
spreading in every direction. With a zero heuristic it *is* Dijkstra's.

Runs in O((V + E) log V) with a heap, same as Dijkstra's.
"""

import heapq
import itertools
import math
from typing import Callable, Dict, Hashable, List, Sequence, Tuple

Node = Hashable
# Adjacency list: node -> [(neighbour, weight), ...]
Graph = Dict[Node, Sequence[Tuple[Node, float]]]
Heuristic = Callable[[Node, Node], float]


def _zero_heuristic(_node: Node, _target: Node) -> float:
    return 0.0


def astar(
    graph: Graph,
    source: Node,
    target: Node,
    heuristic: Heuristic | None = None,
) -> Tuple[List[Node], float]:
    """Return ``(path, cost)`` for a shortest path ``source`` -> ``target``.

    ``heuristic(node, target)`` estimates the remaining cost from
    ``node`` to ``target``. It must never overestimate the true cost
    (admissible) for the returned path to be optimal; the default
    zero heuristic is always admissible and makes this Dijkstra's.

    Returns ``([], math.inf)`` when ``target`` is unreachable from
    ``source`` — including when ``target`` is not in the graph at all.
    Raises ``KeyError`` if ``source`` is not in the graph and
    ``ValueError`` on a negative edge weight.
    """
    if source not in graph:
        raise KeyError(f"source {source!r} not in graph")
    if heuristic is None:
        heuristic = _zero_heuristic

    # g_score: cheapest known cost source -> node.
    g_score: Dict[Node, float] = {source: 0.0}
    predecessors: Dict[Node, Node] = {}
    # Heap entries are (f_score, tie-breaker, node); the counter keeps
    # nodes with equal f_scores from ever being compared to each other.
    counter = itertools.count()
    heap: List[Tuple[float, int, Node]] = [
        (heuristic(source, target), next(counter), source)
    ]
    closed: set = set()

    while heap:
        _, _, node = heapq.heappop(heap)
        if node in closed:
            continue
        closed.add(node)
        if node == target:
            break
        for neighbour, weight in graph.get(node, []):
            if weight < 0:
                raise ValueError(
                    f"negative edge weight {weight} on {node!r} -> {neighbour!r}"
                )
            new_g = g_score[node] + weight
            if new_g < g_score.get(neighbour, math.inf):
                g_score[neighbour] = new_g
                predecessors[neighbour] = node
                f_score = new_g + heuristic(neighbour, target)
                heapq.heappush(heap, (f_score, next(counter), neighbour))

    if target not in g_score:
        return [], math.inf
    path = [target]
    while path[-1] != source:
        path.append(predecessors[path[-1]])
    path.reverse()
    return path, g_score[target]


def astar_path(
    graph: Graph,
    source: Node,
    target: Node,
    heuristic: Heuristic | None = None,
) -> List[Node]:
    """Return the list of nodes on a shortest path ``source`` -> ``target``.

    Returns ``[]`` when ``target`` is unreachable from ``source``.
    """
    path, _ = astar(graph, source, target, heuristic)
    return path
