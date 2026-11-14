import math
import random

import pytest

from dsa.bellman_ford import bellman_ford
from dsa.dijkstra import dijkstra
from dsa.floyd_warshall import floyd_warshall, shortest_path

# Small graph used by most tests — the Bellman-Ford test graph:
#   A --1-- B --2-- D
#   |       |       |
#   4       1       1
#   |       |       |
#   C --1-- E --3-- F   (plus C -> B at -2)
GRAPH = {
    "A": [("B", 1), ("C", 4)],
    "B": [("A", 1), ("D", 2), ("E", 1)],
    "C": [("A", 4), ("E", 1), ("B", -2)],
    "D": [("B", 2), ("F", 1)],
    "E": [("B", 1), ("C", 1), ("F", 3)],
    "F": [("D", 1), ("E", 3)],
}


def test_diagonal_is_zero():
    distances, _ = floyd_warshall(GRAPH)
    for node in GRAPH:
        assert distances[node][node] == 0


def test_negative_edge_is_used():
    # S->M->T = 2 + (-3) = -1 beats the direct S->T = 5.
    graph = {"S": [("T", 5), ("M", 2)], "M": [("T", -3)], "T": []}
    distances, _ = floyd_warshall(graph)
    assert distances["S"]["T"] == -1
    assert distances["S"]["M"] == 2
    assert distances["M"]["T"] == -3


def test_matches_dijkstra_row_on_non_negative_graph():
    # On weights Dijkstra accepts, each Floyd-Warshall row must agree
    # with Dijkstra run from that source.
    graph = {
        "A": [("B", 1), ("C", 4)],
        "B": [("A", 1), ("D", 2), ("E", 1)],
        "C": [("A", 4), ("E", 1)],
        "D": [("B", 2), ("F", 1)],
        "E": [("B", 1), ("C", 1), ("F", 3)],
        "F": [("D", 1), ("E", 3)],
    }
    distances, _ = floyd_warshall(graph)
    for source in graph:
        dj_dist, _ = dijkstra(graph, source)
        assert distances[source] == dj_dist


def test_matches_bellman_ford_row_on_negative_graph():
    # Same check against Bellman-Ford, which accepts the negative edge.
    distances, _ = floyd_warshall(GRAPH)
    for source in GRAPH:
        bf_dist, _ = bellman_ford(GRAPH, source)
        assert distances[source] == bf_dist


def test_unreachable_pairs_are_inf():
    graph = {"A": [("B", 1)], "B": [], "C": []}
    distances, next_hop = floyd_warshall(graph)
    assert distances["A"]["B"] == 1
    assert distances["A"]["C"] == math.inf
    assert distances["C"]["A"] == math.inf
    assert "C" not in next_hop["A"]


def test_single_node_and_empty_graph():
    distances, next_hop = floyd_warshall({"A": []})
    assert distances == {"A": {"A": 0}}
    assert next_hop == {"A": {}}
    assert floyd_warshall({}) == ({}, {})


def test_negative_cycle_raises():
    # A -> B (1), B -> C (-1), C -> A (-1): every lap drops the total
    # by 1, so no shortest path exists.
    graph = {"A": [("B", 1)], "B": [("C", -1)], "C": [("A", -1)]}
    with pytest.raises(ValueError, match="negative cycle"):
        floyd_warshall(graph)


def test_zero_weight_edges_work():
    graph = {"A": [("B", 0)], "B": [("C", 0)], "C": []}
    distances, _ = floyd_warshall(graph)
    assert distances["A"]["C"] == 0
    assert distances["B"]["C"] == 0


def test_shortest_path_reconstruction():
    assert shortest_path(GRAPH, "A", "F") == ["A", "B", "D", "F"]
    assert shortest_path(GRAPH, "A", "E") == ["A", "B", "E"]
    assert shortest_path(GRAPH, "C", "D") == ["C", "B", "D"]


def test_shortest_path_uses_negative_edge():
    graph = {"S": [("T", 5), ("M", 2)], "M": [("T", -3)], "T": []}
    assert shortest_path(graph, "S", "T") == ["S", "M", "T"]


def test_shortest_path_to_self_and_unreachable():
    assert shortest_path(GRAPH, "A", "A") == ["A"]
    assert shortest_path({"A": [], "B": []}, "A", "B") == []


def test_unknown_source_raises():
    with pytest.raises(KeyError):
        shortest_path(GRAPH, "Z", "A")


def test_path_cost_matches_distances():
    distances, _ = floyd_warshall(GRAPH)
    path = shortest_path(GRAPH, "A", "F")
    cost = sum(dict(GRAPH[u])[v] for u, v in zip(path, path[1:]))
    assert cost == distances["A"]["F"] == 4


def test_matches_dijkstra_on_random_non_negative_graphs():
    # Floyd-Warshall and Dijkstra must agree wherever Dijkstra applies.
    rng = random.Random(42)
    for _ in range(20):
        n = rng.randint(2, 7)
        nodes = [chr(ord("A") + i) for i in range(n)]
        graph = {node: [] for node in nodes}
        for u in nodes:
            for v in nodes:
                if u != v and rng.random() < 0.4:
                    graph[u].append((v, rng.randint(0, 9)))
        distances, _ = floyd_warshall(graph)
        for source in nodes:
            dj_dist, _ = dijkstra(graph, source)
            # Dijkstra omits unreachable nodes; Floyd-Warshall marks
            # them inf — compare reachable entries, then check the rest.
            for node, dist in dj_dist.items():
                assert distances[source][node] == dist
            for node in nodes:
                if node not in dj_dist:
                    assert distances[source][node] == math.inf
