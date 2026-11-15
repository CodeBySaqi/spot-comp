"""Topological sort (Kahn's algorithm) for directed acyclic graphs.

Classic ARIN-1108 graph algorithm: given a directed graph, return an
ordering of the nodes so that every edge ``u -> v`` has ``u`` before
``v`` — the order in which tasks with prerequisites, course modules,
or build steps must run. Runs in O(V + E). Uses Kahn's algorithm:
repeatedly emit a node with no remaining prerequisites, then drop
its outgoing edges. If no such node exists while nodes remain, the
graph has a cycle and no topological ordering exists.
"""

from collections import deque
from typing import Dict, Hashable, List, Sequence, Tuple

Node = Hashable
# Adjacency list: node -> [neighbour, ...] (edge node -> neighbour)
Graph = Dict[Node, Sequence[Node]]


def topological_sort(graph: Graph) -> List[Node]:
    """Return a topological ordering of ``graph``.

    Every node named anywhere in the graph — as a key or only as a
    neighbour — appears exactly once in the result, and for every
    edge ``u -> v``, ``u`` comes before ``v``.

    Raises ``ValueError`` if the graph contains a cycle (including a
    self-loop), naming one node left unplaced when the sort stalls.
    """
    # Every node named anywhere in the graph, keys and neighbours alike.
    nodes = list(graph)
    seen = set(nodes)
    for neighbours in graph.values():
        for neighbour in neighbours:
            if neighbour not in seen:
                seen.add(neighbour)
                nodes.append(neighbour)

    in_degree: Dict[Node, int] = {node: 0 for node in nodes}
    for u, neighbours in graph.items():
        for v in neighbours:
            in_degree[v] += 1

    # Nodes with no prerequisites, in first-seen order so the result
    # is deterministic for a given graph.
    ready = deque(node for node in nodes if in_degree[node] == 0)
    order: List[Node] = []

    while ready:
        u = ready.popleft()
        order.append(u)
        for v in graph.get(u, ()):  # neighbours-only nodes have no edges
            in_degree[v] -= 1
            if in_degree[v] == 0:
                ready.append(v)

    if len(order) != len(nodes):
        stalled = next(node for node in nodes if node not in order)
        raise ValueError(f"graph contains a cycle involving {stalled!r}")

    return order


def is_dag(graph: Graph) -> bool:
    """Return ``True`` when ``graph`` has a topological ordering."""
    try:
        topological_sort(graph)
    except ValueError:
        return False
    return True
