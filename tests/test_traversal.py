import pytest

from dsa.traversal import bfs, bfs_path, dfs


# Small graph used by most tests:
#   A -- B -- D
#   |    |    |
#   C -- F -- E   (E hangs off B, F off C)
GRAPH = {
    "A": ["B", "C"],
    "B": ["A", "D", "E"],
    "C": ["A", "F"],
    "D": ["B"],
    "E": ["B", "F"],
    "F": ["C", "E"],
}


def test_bfs_visits_level_by_level():
    order, levels = bfs(GRAPH, "A")
    assert order == ["A", "B", "C", "D", "E", "F"]
    assert levels == {"A": 0, "B": 1, "C": 1, "D": 2, "E": 2, "F": 2}


def test_bfs_levels_are_edge_distances():
    order, levels = bfs(GRAPH, "D")
    # D -> B (1) -> A, E (2) -> C, F (3)
    assert levels == {"D": 0, "B": 1, "A": 2, "E": 2, "C": 3, "F": 3}
    assert order[0] == "D"
    assert set(order) == set(GRAPH)


def test_bfs_unreachable_nodes_are_absent():
    graph = {"A": ["B"], "B": [], "C": []}
    order, levels = bfs(graph, "A")
    assert order == ["A", "B"]
    assert levels == {"A": 0, "B": 1}


def test_bfs_single_node_graph():
    order, levels = bfs({"A": []}, "A")
    assert order == ["A"]
    assert levels == {"A": 0}


def test_bfs_unknown_source_raises():
    with pytest.raises(KeyError):
        bfs(GRAPH, "Z")


def test_bfs_neighbour_only_node_is_a_leaf():
    # "B" never appears as a key, so it has no neighbours of its own.
    order, levels = bfs({"A": ["B"]}, "A")
    assert order == ["A", "B"]
    assert levels == {"A": 0, "B": 1}


def test_dfs_goes_deep_before_wide():
    # A -> B -> D first, then backtrack: E, F, C.
    assert dfs(GRAPH, "A") == ["A", "B", "D", "E", "F", "C"]


def test_dfs_visits_each_reachable_node_once():
    order = dfs(GRAPH, "A")
    assert sorted(order) == sorted(GRAPH)
    assert len(order) == len(set(order))


def test_dfs_unreachable_nodes_are_absent():
    graph = {"A": ["B"], "B": [], "C": []}
    assert dfs(graph, "A") == ["A", "B"]


def test_dfs_unknown_source_raises():
    with pytest.raises(KeyError):
        dfs(GRAPH, "Z")


def test_bfs_path_is_shortest_by_edges():
    # A -> C -> F is 2 edges; the A -> B -> E -> F route is 3.
    assert bfs_path(GRAPH, "A", "F") == ["A", "C", "F"]
    assert bfs_path(GRAPH, "A", "E") == ["A", "B", "E"]


def test_bfs_path_length_matches_levels():
    _, levels = bfs(GRAPH, "A")
    for target in GRAPH:
        path = bfs_path(GRAPH, "A", target)
        assert len(path) - 1 == levels[target]


def test_bfs_path_to_self_and_unreachable():
    assert bfs_path(GRAPH, "A", "A") == ["A"]
    assert bfs_path({"A": [], "B": []}, "A", "B") == []


def test_bfs_path_unknown_source_raises():
    with pytest.raises(KeyError):
        bfs_path(GRAPH, "Z", "A")
