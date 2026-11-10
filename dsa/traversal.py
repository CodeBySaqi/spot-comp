"""Breadth-first and depth-first graph traversal.

Classic ARIN-1108 graph algorithms, the natural companion to Dijkstra:
BFS explores level by level (and so finds shortest paths in an
unweighted graph), DFS goes as deep as possible before backtracking.
Both run in O(V + E). The graph is an unweighted adjacency list:
``node -> [neighbour, ...]``. A node that only appears as a neighbour
(never as a key) is treated as a leaf.
"""

from collections import deque
from typing import Dict, Hashable, List, Sequence, Tuple

Node = Hashable
# Adjacency list: node -> [neighbour, ...]
Graph = Dict[Node, Sequence[Node]]


def bfs(graph: Graph, source: Node) -> Tuple[List[Node], Dict[Node, int]]:
    """Return ``(order, levels)`` for a breadth-first walk from ``source``.

    ``order`` lists every node reachable from ``source`` in the order
    first visited; ``levels`` maps each reached node to its distance
    from ``source`` in edges (``source`` itself is level 0).
    Unreachable nodes are absent from both.

    Raises ``KeyError`` if ``source`` is not in the graph.
    """
    if source not in graph:
        raise KeyError(f"source {source!r} not in graph")

    order: List[Node] = [source]
    levels: Dict[Node, int] = {source: 0}
    queue: deque = deque([source])

    while queue:
        node = queue.popleft()
        for neighbour in graph.get(node, []):
            if neighbour not in levels:
                levels[neighbour] = levels[node] + 1
                order.append(neighbour)
                queue.append(neighbour)

    return order, levels


def dfs(graph: Graph, source: Node) -> List[Node]:
    """Return the nodes reachable from ``source`` in depth-first order.

    Iterative (explicit stack, no recursion limit). Neighbours are
    visited in the order listed in the adjacency list, so the result
    is deterministic for a given graph. Unreachable nodes are absent.

    Raises ``KeyError`` if ``source`` is not in the graph.
    """
    if source not in graph:
        raise KeyError(f"source {source!r} not in graph")

    order: List[Node] = []
    seen = {source}
    stack: List[Node] = [source]

    while stack:
        node = stack.pop()
        order.append(node)
        # Push reversed so the first-listed neighbour is popped first.
        for neighbour in reversed(graph.get(node, [])):
            if neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)

    return order


def bfs_path(graph: Graph, source: Node, target: Node) -> List[Node]:
    """Return a shortest path ``source`` -> ``target`` (fewest edges).

    Returns ``[source]`` when ``source == target`` and ``[]`` when
    ``target`` is unreachable from ``source``.
    """
    if source not in graph:
        raise KeyError(f"source {source!r} not in graph")
    if source == target:
        return [source]

    predecessors: Dict[Node, Node] = {}
    queue: deque = deque([source])
    seen = {source}

    while queue:
        node = queue.popleft()
        for neighbour in graph.get(node, []):
            if neighbour not in seen:
                seen.add(neighbour)
                predecessors[neighbour] = node
                if neighbour == target:
                    path = [target]
                    while path[-1] != source:
                        path.append(predecessors[path[-1]])
                    path.reverse()
                    return path
                queue.append(neighbour)

    return []
