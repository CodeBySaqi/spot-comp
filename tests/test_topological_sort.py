import random

import pytest

from dsa.topological_sort import is_dag, topological_sort


def assert_valid_order(graph, order):
    """Every node once, and every edge u -> v has u before v."""
    nodes = set(graph)
    for neighbours in graph.values():
        nodes.update(neighbours)
    assert sorted(order, key=str) == sorted(nodes, key=str)
    position = {node: i for i, node in enumerate(order)}
    for u, neighbours in graph.items():
        for v in neighbours:
            assert position[u] < position[v]


# Diamond used by most tests:
#   A -> B -> D
#   A -> C -> D   (plus D -> E)
GRAPH = {
    "A": ["B", "C"],
    "B": ["D"],
    "C": ["D"],
    "D": ["E"],
    "E": [],
}


def test_diamond_is_valid():
    assert_valid_order(GRAPH, topological_sort(GRAPH))


def test_a_comes_first_and_e_last():
    order = topological_sort(GRAPH)
    assert order[0] == "A"
    assert order[-1] == "E"


def test_linear_chain_has_one_order():
    graph = {"A": ["B"], "B": ["C"], "C": ["D"], "D": []}
    assert topological_sort(graph) == ["A", "B", "C", "D"]


def test_disconnected_nodes_all_appear():
    graph = {"A": ["B"], "B": [], "C": [], "D": ["E"], "E": []}
    assert_valid_order(graph, topological_sort(graph))


def test_neighbour_only_node_is_included():
    # "B" is never a key, only a neighbour — it must still appear.
    assert topological_sort({"A": ["B"]}) == ["A", "B"]


def test_single_node_and_empty_graph():
    assert topological_sort({"A": []}) == ["A"]
    assert topological_sort({}) == []


def test_self_loop_raises():
    with pytest.raises(ValueError, match="cycle"):
        topological_sort({"A": ["A"]})


def test_two_node_cycle_raises():
    with pytest.raises(ValueError, match="cycle"):
        topological_sort({"A": ["B"], "B": ["A"]})


def test_three_node_cycle_raises():
    graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
    with pytest.raises(ValueError, match="cycle"):
        topological_sort(graph)


def test_cycle_elsewhere_still_raises():
    # A -> B is fine, but C <-> D is a cycle, so no order exists.
    graph = {"A": ["B"], "B": [], "C": ["D"], "D": ["C"]}
    with pytest.raises(ValueError, match="cycle"):
        topological_sort(graph)


def test_is_dag_agrees():
    assert is_dag(GRAPH) is True
    assert is_dag({}) is True
    assert is_dag({"A": ["B"], "B": ["A"]}) is False
    assert is_dag({"A": ["A"]}) is False


def test_duplicate_edges_do_not_break_it():
    # A -> B listed twice must not double-count the in-degree.
    graph = {"A": ["B", "B"], "B": []}
    assert topological_sort(graph) == ["A", "B"]


def test_prerequisite_chain_from_course_modules():
    # ARIN-1108 style: Logic -> DSA -> Graphs -> Shortest Paths.
    graph = {
        "Logic": ["DSA"],
        "DSA": ["Graphs"],
        "Graphs": ["Shortest Paths"],
        "Shortest Paths": [],
    }
    assert topological_sort(graph) == [
        "Logic",
        "DSA",
        "Graphs",
        "Shortest Paths",
    ]


def test_valid_on_random_dags():
    # Random DAGs (edges only i -> j with i < j) must always sort validly.
    rng = random.Random(42)
    for _ in range(20):
        n = rng.randint(2, 8)
        nodes = [chr(ord("A") + i) for i in range(n)]
        graph = {node: [] for node in nodes}
        for i, u in enumerate(nodes):
            for v in nodes[i + 1 :]:
                if rng.random() < 0.4:
                    graph[u].append(v)
        assert_valid_order(graph, topological_sort(graph))
