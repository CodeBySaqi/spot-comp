"""Graph colouring (greedy + exact).

Classic ARIN-1108 graph problem: colour every vertex so that no edge
joins two vertices of the same colour — the same constraint behind
exam timetabling (no two clashing exams in one slot), register
allocation, and map colouring. The graph is an unweighted adjacency
list: ``node -> [neighbour, ...]``, the same shape as ``traversal.py``
and ``kruskal.py``. A node that only appears as a neighbour (never as
a key) is still a vertex and gets a colour.

``greedy_coloring`` colours in Welsh-Powell order — highest degree
first — which never uses more than ``max_degree + 1`` colours and is
fast enough for large graphs. ``chromatic_number`` and
``min_coloring`` are exact, by backtracking: they try ``k = 1, 2, ...``
from a greedy-clique lower bound until a colouring fits, so they are
only practical on small graphs (a dozen or so vertices), which is
where the exact answer is worth knowing. ``is_k_colorable`` is the
decision version of the same search.
"""

from typing import Dict, Hashable, List, Optional, Sequence, Set

Node = Hashable
# Adjacency list: node -> [neighbour, ...]
Graph = Dict[Node, Sequence[Node]]


def _vertices(graph: Graph) -> List[Node]:
    """Every vertex: keys plus nodes that only appear as neighbours."""
    seen: Set[Node] = set(graph)
    for neighbours in graph.values():
        seen.update(neighbours)
    # Deterministic order: sort by repr so results do not depend on
    # hash randomisation between runs.
    return sorted(seen, key=repr)


def _adjacency(graph: Graph) -> Dict[Node, Set[Node]]:
    """Symmetric adjacency: every listed edge counts in both directions.

    An edge listed once (``0: [1, 2]`` with ``1: [0]`` and no key for
    ``2``) still joins 0 and 2, so 2's neighbours must include 0 even
    though 2 has no entry of its own.
    """
    adj: Dict[Node, Set[Node]] = {v: set() for v in _vertices(graph)}
    for vertex, neighbours in graph.items():
        for neighbour in neighbours:
            adj[vertex].add(neighbour)
            adj[neighbour].add(vertex)
    return adj


def _has_self_loop(graph: Graph) -> bool:
    return any(vertex in neighbours for vertex, neighbours in graph.items())


def greedy_coloring(graph: Graph, order: Optional[Sequence[Node]] = None) -> Dict[Node, int]:
    """Colour ``graph`` greedily, returning ``{node: colour}`` (0-based).

    Vertices are coloured in the given ``order`` when supplied, else
    Welsh-Powell order: highest degree first, ties broken by the
    deterministic vertex order. Each vertex takes the smallest colour
    none of its already-coloured neighbours uses, so the result is
    always valid and uses at most ``max_degree + 1`` colours.
    """
    vertices = _vertices(graph)
    adj = _adjacency(graph)
    if order is None:
        degree = {v: len(adj[v]) for v in vertices}
        order = sorted(vertices, key=lambda v: (-degree[v], repr(v)))
    else:
        order = [v for v in order if v in set(vertices)]
        missing = [v for v in vertices if v not in set(order)]
        order = list(order) + missing
    coloring: Dict[Node, int] = {}
    for vertex in order:
        used = {coloring[n] for n in adj[vertex] if n in coloring}
        colour = 0
        while colour in used:
            colour += 1
        coloring[vertex] = colour
    return coloring


def is_valid_coloring(graph: Graph, coloring: Dict[Node, int]) -> bool:
    """Return ``True`` when every vertex is coloured and no edge is monochromatic.

    A self-loop makes any colouring invalid, since a vertex cannot
    differ in colour from itself.
    """
    vertices = _vertices(graph)
    if any(v not in coloring for v in vertices):
        return False
    adj = _adjacency(graph)
    for vertex in vertices:
        if vertex in adj[vertex]:
            return False
        for neighbour in adj[vertex]:
            if coloring[vertex] == coloring[neighbour]:
                return False
    return True


def num_colors(coloring: Dict[Node, int]) -> int:
    """Return how many distinct colours a colouring uses (0 when empty)."""
    return len(set(coloring.values()))


def _color_with_k(graph: Graph, k: int) -> Optional[Dict[Node, int]]:
    """Backtracking search for a colouring using at most ``k`` colours.

    Returns the colouring, or ``None`` when none exists. Vertices are
    tried highest-degree first, which prunes the search hard on the
    small graphs this is meant for.
    """
    vertices = _vertices(graph)
    if _has_self_loop(graph):
        return None
    if k <= 0:
        return {} if not vertices else None
    adj = _adjacency(graph)
    degree = {v: len(adj[v]) for v in vertices}
    order = sorted(vertices, key=lambda v: (-degree[v], repr(v)))
    coloring: Dict[Node, int] = {}

    def search(i: int) -> bool:
        if i == len(order):
            return True
        vertex = order[i]
        used = {coloring[n] for n in adj[vertex] if n in coloring}
        for colour in range(k):
            if colour not in used:
                coloring[vertex] = colour
                if search(i + 1):
                    return True
                del coloring[vertex]
        return False

    return dict(coloring) if search(0) else None


def is_k_colorable(graph: Graph, k: int) -> bool:
    """Return ``True`` when ``graph`` can be coloured with ``k`` colours."""
    return _color_with_k(graph, k) is not None


def _greedy_clique_size(graph: Graph) -> int:
    """Size of a greedily built clique — a lower bound on the colours needed.

    Any clique needs one colour per vertex, so the chromatic number is
    at least this large. Used only to start the exact search higher
    than 1 on dense graphs.
    """
    vertices = _vertices(graph)
    adj = _adjacency(graph)
    best = 0
    for start in vertices:
        clique = [start]
        candidates = [v for v in vertices if v != start and v in adj[start]]
        for v in sorted(candidates, key=repr):
            if all(v in adj[c] for c in clique):
                clique.append(v)
        best = max(best, len(clique))
    return best


def chromatic_number(graph: Graph) -> int:
    """Return the smallest number of colours that can colour ``graph``.

    Exact, by trying ``k`` from a greedy-clique lower bound upwards.
    0 for an empty graph, 1 for a non-empty graph with no edges.
    Only practical on small graphs (roughly a dozen vertices).
    Raises ``ValueError`` on a self-loop, which no colouring can satisfy.
    """
    vertices = _vertices(graph)
    if not vertices:
        return 0
    if _has_self_loop(graph):
        raise ValueError("graph with a self-loop cannot be coloured")
    adj = _adjacency(graph)
    if not any(adj[v] for v in vertices):
        return 1
    lower = max(2, _greedy_clique_size(graph))
    for k in range(lower, len(vertices) + 1):
        if is_k_colorable(graph, k):
            return k
    return len(vertices)


def min_coloring(graph: Graph) -> Dict[Node, int]:
    """Return a colouring of ``graph`` using exactly its chromatic number of colours."""
    k = chromatic_number(graph)
    coloring = _color_with_k(graph, k)
    assert coloring is not None  # chromatic_number just proved k works
    return coloring
