import itertools
import random

import pytest

from dsa.graph_coloring import (
    chromatic_number,
    greedy_coloring,
    is_k_colorable,
    is_valid_coloring,
    min_coloring,
    num_colors,
)


def _complete_graph(n):
    return {v: [u for u in range(n) if u != v] for v in range(n)}


def _cycle_graph(n):
    return {v: [(v - 1) % n, (v + 1) % n] for v in range(n)}


def _path_graph(n):
    graph = {}
    for v in range(n):
        neighbours = []
        if v > 0:
            neighbours.append(v - 1)
        if v < n - 1:
            neighbours.append(v + 1)
        graph[v] = neighbours
    return graph


def _brute_force_chromatic_number(graph):
    """Exhaustive check: smallest k with a valid k-colouring, by trying all assignments."""
    vertices = sorted(set(graph) | {n for ns in graph.values() for n in ns}, key=repr)
    if not vertices:
        return 0
    for k in range(len(vertices) + 1):
        for assignment in itertools.product(range(k), repeat=len(vertices)):
            coloring = dict(zip(vertices, assignment))
            if is_valid_coloring(graph, coloring):
                return k
    return len(vertices)


def test_complete_graph_needs_one_colour_per_vertex():
    assert chromatic_number(_complete_graph(4)) == 4
    assert num_colors(greedy_coloring(_complete_graph(4))) == 4
    assert is_valid_coloring(_complete_graph(4), greedy_coloring(_complete_graph(4)))
    assert chromatic_number(_complete_graph(1)) == 1
    assert not is_k_colorable(_complete_graph(4), 3)
    assert is_k_colorable(_complete_graph(4), 4)


def test_bipartite_graphs_need_two_colours():
    # Even cycle and path are bipartite: 2 colours, never 1.
    assert chromatic_number(_cycle_graph(4)) == 2
    assert chromatic_number(_path_graph(5)) == 2
    assert num_colors(greedy_coloring(_cycle_graph(4))) == 2
    assert not is_k_colorable(_cycle_graph(4), 1)
    assert is_k_colorable(_path_graph(5), 2)


def test_odd_cycle_needs_three_colours():
    # C5 is the smallest non-bipartite cycle: 2 colours cannot work.
    assert chromatic_number(_cycle_graph(5)) == 3
    assert not is_k_colorable(_cycle_graph(5), 2)
    assert is_k_colorable(_cycle_graph(5), 3)
    coloring = min_coloring(_cycle_graph(5))
    assert num_colors(coloring) == 3
    assert is_valid_coloring(_cycle_graph(5), coloring)


def test_empty_and_single_vertex():
    assert chromatic_number({}) == 0
    assert greedy_coloring({}) == {}
    assert min_coloring({}) == {}
    assert num_colors(greedy_coloring({})) == 0
    assert chromatic_number({0: []}) == 1
    assert greedy_coloring({0: []}) == {0: 0}
    assert is_k_colorable({}, 0)
    assert not is_k_colorable({0: []}, 0)


def test_edgeless_graph_uses_one_colour():
    graph = {0: [], 1: [], 2: [], 3: []}
    assert chromatic_number(graph) == 1
    assert num_colors(greedy_coloring(graph)) == 1
    assert is_valid_coloring(graph, greedy_coloring(graph))


def test_disconnected_components():
    # Two separate triangles: each needs 3, together still 3.
    graph = {0: [1, 2], 1: [0, 2], 2: [0, 1], 3: [4, 5], 4: [3, 5], 5: [3, 4]}
    assert chromatic_number(graph) == 3
    assert num_colors(min_coloring(graph)) == 3
    assert is_valid_coloring(graph, min_coloring(graph))


def test_neighbour_only_nodes_get_coloured():
    # Node 2 is never a key, only a neighbour — it is still a vertex.
    graph = {0: [1, 2], 1: [0]}
    coloring = greedy_coloring(graph)
    assert set(coloring) == {0, 1, 2}
    assert is_valid_coloring(graph, coloring)
    assert chromatic_number(graph) == 2


def test_greedy_is_valid_and_within_degree_plus_one():
    rng = random.Random(11)
    for _ in range(30):
        n = rng.randint(1, 12)
        graph = {v: [] for v in range(n)}
        for i in range(n):
            for j in range(i + 1, n):
                if rng.random() < 0.3:
                    graph[i].append(j)
                    graph[j].append(i)
        coloring = greedy_coloring(graph)
        assert is_valid_coloring(graph, coloring)
        max_degree = max((len(ns) for ns in graph.values()), default=0)
        assert num_colors(coloring) <= max_degree + 1
        assert num_colors(coloring) >= chromatic_number(graph)


def test_chromatic_number_matches_brute_force_on_random_graphs():
    rng = random.Random(5)
    for _ in range(30):
        n = rng.randint(0, 7)
        graph = {v: [] for v in range(n)}
        for i in range(n):
            for j in range(i + 1, n):
                if rng.random() < 0.4:
                    graph[i].append(j)
                    graph[j].append(i)
        assert chromatic_number(graph) == _brute_force_chromatic_number(graph)
        coloring = min_coloring(graph)
        assert num_colors(coloring) == chromatic_number(graph)
        assert is_valid_coloring(graph, coloring)


def test_min_coloring_uses_fewest_colours():
    # The classic "house" graph (square + roof triangle) needs 3.
    graph = {0: [1, 3], 1: [0, 2, 4], 2: [1, 3, 4], 3: [0, 2], 4: [1, 2]}
    assert chromatic_number(graph) == 3
    coloring = min_coloring(graph)
    assert num_colors(coloring) == 3
    assert is_valid_coloring(graph, coloring)


def test_invalid_colourings_are_rejected():
    graph = _cycle_graph(4)
    assert not is_valid_coloring(graph, {0: 0, 1: 0, 2: 1, 3: 1})
    # Missing a vertex is not a colouring at all.
    assert not is_valid_coloring(graph, {0: 0, 1: 1, 2: 0})
    # A self-loop can never be coloured.
    assert not is_valid_coloring({0: [0]}, {0: 0})
    assert not is_k_colorable({0: [0]}, 1)


def test_custom_order_is_respected_when_possible():
    # Colouring in the order given still produces a valid result.
    graph = _cycle_graph(4)
    coloring = greedy_coloring(graph, order=[2, 0, 3, 1])
    assert set(coloring) == {0, 1, 2, 3}
    assert is_valid_coloring(graph, coloring)


def test_greedy_still_fast_on_large_graph():
    # 200 vertices, sparse: greedy must stay valid and within Δ + 1.
    rng = random.Random(9)
    n = 200
    graph = {v: [] for v in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < 0.02:
                graph[i].append(j)
                graph[j].append(i)
    coloring = greedy_coloring(graph)
    assert is_valid_coloring(graph, coloring)
    max_degree = max(len(ns) for ns in graph.values())
    assert num_colors(coloring) <= max_degree + 1
