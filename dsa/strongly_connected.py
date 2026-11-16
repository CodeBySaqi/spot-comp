"""Strongly connected components (Kosaraju's algorithm).

Classic ARIN-1108 graph algorithm: in a directed graph, two nodes are
in the same strongly connected component when each can reach the other.
Kosaraju's algorithm finds every component in O(V + E) with two depth
first searches: the first pass records nodes in finishing order, the
second pass walks the reversed graph in that order, and each walk
collects exactly one component. Components come back in reverse
topological order of the condensation graph — a component with no
incoming edges from other components first.
"""

from typing import Dict, Hashable, List, Sequence

Node = Hashable
# Adjacency list: node -> [neighbour, ...] (edge node -> neighbour)
Graph = Dict[Node, Sequence[Node]]


def _all_nodes(graph: Graph) -> List[Node]:
    """Every node named anywhere in the graph, keys and neighbours alike."""
    nodes = list(graph)
    seen = set(nodes)
    for neighbours in graph.values():
        for neighbour in neighbours:
            if neighbour not in seen:
                seen.add(neighbour)
                nodes.append(neighbour)
    return nodes


def _reverse_graph(graph: Graph, nodes: List[Node]) -> Graph:
    """The graph with every edge flipped, covering all nodes."""
    reversed_graph: Dict[Node, List[Node]] = {node: [] for node in nodes}
    for u, neighbours in graph.items():
        for v in neighbours:
            reversed_graph[v].append(u)
    return reversed_graph


def strongly_connected_components(graph: Graph) -> List[List[Node]]:
    """Return the strongly connected components of ``graph``.

    Each component is a list of nodes, and the components are in
    reverse topological order of the condensation graph. A node on its
    own (no cycle back to it) is a singleton component, and a self-loop
    is still just a singleton — a node is always trivially connected
    to itself.
    """
    nodes = _all_nodes(graph)
    reversed_graph = _reverse_graph(graph, nodes)

    # Pass 1: iterative DFS on the original graph, recording the order
    # in which nodes finish (post-order).
    visited = set()
    finish_order: List[Node] = []
    for start in nodes:
        if start in visited:
            continue
        stack = [(start, iter(graph.get(start, ())))]
        visited.add(start)
        while stack:
            node, neighbours = stack[-1]
            advanced = False
            for neighbour in neighbours:
                if neighbour not in visited:
                    visited.add(neighbour)
                    stack.append((neighbour, iter(graph.get(neighbour, ()))))
                    advanced = True
                    break
            if not advanced:
                finish_order.append(node)
                stack.pop()

    # Pass 2: DFS on the reversed graph, taking nodes in reverse
    # finishing order — each walk collects one whole component.
    assigned = set()
    components: List[List[Node]] = []
    for start in reversed(finish_order):
        if start in assigned:
            continue
        component: List[Node] = []
        stack = [start]
        assigned.add(start)
        while stack:
            node = stack.pop()
            component.append(node)
            for neighbour in reversed_graph.get(node, ()):
                if neighbour not in assigned:
                    assigned.add(neighbour)
                    stack.append(neighbour)
        components.append(component)

    return components


def is_strongly_connected(graph: Graph) -> bool:
    """Return ``True`` when every node in ``graph`` can reach every other."""
    nodes = _all_nodes(graph)
    if not nodes:
        return True
    return len(strongly_connected_components(graph)) == 1
