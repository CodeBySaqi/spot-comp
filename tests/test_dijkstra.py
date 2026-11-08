import pytest

from dsa.dijkstra import dijkstra, shortest_path


# Small graph used by most tests:
#   A --1-- B --2-- D
#   |       |       |
#   4       1       1
#   |       |       |
#   C --1-- E --3-- F   (F only reachable via D or E)
GRAPH = {
    "A": [("B", 1), ("C", 4)],
    "B": [("A", 1), ("D", 2), ("E", 1)],
    "C": [("A", 4), ("E", 1)],
    "D": [("B", 2), ("F", 1)],
    "E": [("B", 1), ("C", 1), ("F", 3)],
    "F": [("D", 1), ("E", 3)],
}


def test_source_distance_is_zero():
    distances, predecessors = dijkstra(GRAPH, "A")
    assert distances["A"] == 0
    assert "A" not in predecessors


def test_shortest_distances():
    distances, _ = dijkstra(GRAPH, "A")
    # A->B = 1, A->B->E = 2, A->B->E->C = 3 beats the direct A->C = 4,
    # A->B->D = 3, A->B->D->F = 4
    assert distances == {"A": 0, "B": 1, "C": 3, "D": 3, "E": 2, "F": 4}


def test_shorter_indirect_route_beats_direct_edge():
    graph = {"S": [("T", 10), ("M", 1)], "M": [("T", 1)], "T": []}
    distances, _ = dijkstra(graph, "S")
    assert distances["T"] == 2


def test_unreachable_nodes_are_absent():
    graph = {"A": [("B", 1)], "B": [], "C": []}
    distances, _ = dijkstra(graph, "A")
    assert distances == {"A": 0, "B": 1}
    assert "C" not in distances


def test_single_node_graph():
    distances, predecessors = dijkstra({"A": []}, "A")
    assert distances == {"A": 0}
    assert predecessors == {}


def test_unknown_source_raises():
    with pytest.raises(KeyError):
        dijkstra(GRAPH, "Z")


def test_negative_weight_raises():
    graph = {"A": [("B", -1)], "B": []}
    with pytest.raises(ValueError, match="negative edge weight"):
        dijkstra(graph, "A")


def test_zero_weight_edges_work():
    graph = {"A": [("B", 0)], "B": [("C", 0)], "C": []}
    distances, _ = dijkstra(graph, "A")
    assert distances == {"A": 0, "B": 0, "C": 0}


def test_shortest_path_reconstruction():
    assert shortest_path(GRAPH, "A", "F") == ["A", "B", "D", "F"]
    assert shortest_path(GRAPH, "A", "E") == ["A", "B", "E"]


def test_shortest_path_to_self_and_unreachable():
    assert shortest_path(GRAPH, "A", "A") == ["A"]
    assert shortest_path({"A": [], "B": []}, "A", "B") == []


def test_path_cost_matches_distances():
    distances, _ = dijkstra(GRAPH, "A")
    path = shortest_path(GRAPH, "A", "F")
    cost = sum(
        dict(GRAPH[u])[v] for u, v in zip(path, path[1:])
    )
    assert cost == distances["F"] == 4
