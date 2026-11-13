import random

import pytest

from dsa.bellman_ford import bellman_ford, shortest_path
from dsa.dijkstra import dijkstra

# Small graph used by most tests — the Dijkstra test graph plus a
# negative edge C -> B, which Dijkstra would reject outright:
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


def test_source_distance_is_zero():
    distances, predecessors = bellman_ford(GRAPH, "A")
    assert distances["A"] == 0
    assert "A" not in predecessors


def test_negative_edge_is_used():
    # S->M->T = 2 + (-3) = -1 beats the direct S->T = 5.
    graph = {"S": [("T", 5), ("M", 2)], "M": [("T", -3)], "T": []}
    distances, _ = bellman_ford(graph, "S")
    assert distances == {"S": 0, "M": 2, "T": -1}


def test_matches_dijkstra_on_non_negative_graph():
    # On weights Dijkstra accepts, the two must agree exactly.
    graph = {
        "A": [("B", 1), ("C", 4)],
        "B": [("A", 1), ("D", 2), ("E", 1)],
        "C": [("A", 4), ("E", 1)],
        "D": [("B", 2), ("F", 1)],
        "E": [("B", 1), ("C", 1), ("F", 3)],
        "F": [("D", 1), ("E", 3)],
    }
    bf_dist, _ = bellman_ford(graph, "A")
    dj_dist, _ = dijkstra(graph, "A")
    assert bf_dist == dj_dist


def test_unreachable_nodes_are_absent():
    graph = {"A": [("B", 1)], "B": [], "C": []}
    distances, _ = bellman_ford(graph, "A")
    assert distances == {"A": 0, "B": 1}
    assert "C" not in distances


def test_single_node_graph():
    distances, predecessors = bellman_ford({"A": []}, "A")
    assert distances == {"A": 0}
    assert predecessors == {}


def test_unknown_source_raises():
    with pytest.raises(KeyError):
        bellman_ford(GRAPH, "Z")


def test_negative_cycle_raises():
    # A -> B (1), B -> C (-1), C -> A (-1): every lap drops the total
    # by 1, so no shortest path exists.
    graph = {"A": [("B", 1)], "B": [("C", -1)], "C": [("A", -1)]}
    with pytest.raises(ValueError, match="negative cycle"):
        bellman_ford(graph, "A")


def test_unreachable_negative_cycle_is_ignored():
    # Same cycle as above, but the source cannot reach it.
    graph = {
        "S": [("T", 3)],
        "T": [],
        "A": [("B", 1)],
        "B": [("C", -1)],
        "C": [("A", -1)],
    }
    distances, _ = bellman_ford(graph, "S")
    assert distances == {"S": 0, "T": 3}


def test_zero_weight_edges_work():
    graph = {"A": [("B", 0)], "B": [("C", 0)], "C": []}
    distances, _ = bellman_ford(graph, "A")
    assert distances == {"A": 0, "B": 0, "C": 0}


def test_shortest_path_reconstruction():
    assert shortest_path(GRAPH, "A", "F") == ["A", "B", "D", "F"]
    assert shortest_path(GRAPH, "A", "E") == ["A", "B", "E"]


def test_shortest_path_uses_negative_edge():
    graph = {"S": [("T", 5), ("M", 2)], "M": [("T", -3)], "T": []}
    assert shortest_path(graph, "S", "T") == ["S", "M", "T"]


def test_shortest_path_to_self_and_unreachable():
    assert shortest_path(GRAPH, "A", "A") == ["A"]
    assert shortest_path({"A": [], "B": []}, "A", "B") == []


def test_path_cost_matches_distances():
    distances, _ = bellman_ford(GRAPH, "A")
    path = shortest_path(GRAPH, "A", "F")
    cost = sum(dict(GRAPH[u])[v] for u, v in zip(path, path[1:]))
    assert cost == distances["F"] == 4


def test_matches_dijkstra_on_random_non_negative_graphs():
    # Bellman-Ford and Dijkstra must agree wherever Dijkstra applies.
    rng = random.Random(42)
    for _ in range(20):
        n = rng.randint(2, 7)
        nodes = [chr(ord("A") + i) for i in range(n)]
        graph = {node: [] for node in nodes}
        for u in nodes:
            for v in nodes:
                if u != v and rng.random() < 0.4:
                    graph[u].append((v, rng.randint(0, 9)))
        bf_dist, _ = bellman_ford(graph, nodes[0])
        dj_dist, _ = dijkstra(graph, nodes[0])
        assert bf_dist == dj_dist
