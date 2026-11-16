import random

import pytest

from dsa.strongly_connected import (
    is_strongly_connected,
    strongly_connected_components,
)


def as_sets(components):
    """Components as a frozenset of frozensets, ignoring order."""
    return frozenset(frozenset(component) for component in components)


# Classic example: {A, B, C} cycle together, D -> E on their own,
# and F alone. Edges: A -> B -> C -> A, C -> D, D -> E.
GRAPH = {
    "A": ["B"],
    "B": ["C"],
    "C": ["A", "D"],
    "D": ["E"],
    "E": [],
    "F": [],
}


def test_classic_example():
    assert as_sets(strongly_connected_components(GRAPH)) == frozenset(
        [frozenset({"A", "B", "C"}), frozenset({"D"}), frozenset({"E"}), frozenset({"F"})]
    )


def test_components_cover_every_node_once():
    components = strongly_connected_components(GRAPH)
    flat = [node for component in components for node in component]
    assert sorted(flat, key=str) == ["A", "B", "C", "D", "E", "F"]


def test_two_node_cycle_is_one_component():
    graph = {"A": ["B"], "B": ["A"]}
    assert as_sets(strongly_connected_components(graph)) == frozenset(
        [frozenset({"A", "B"})]
    )


def test_two_node_one_way_is_two_components():
    graph = {"A": ["B"], "B": []}
    assert as_sets(strongly_connected_components(graph)) == frozenset(
        [frozenset({"A"}), frozenset({"B"})]
    )


def test_linear_chain_all_singletons():
    graph = {"A": ["B"], "B": ["C"], "C": ["D"], "D": []}
    components = strongly_connected_components(graph)
    assert len(components) == 4
    assert all(len(component) == 1 for component in components)


def test_single_node_and_empty_graph():
    assert strongly_connected_components({"A": []}) == [["A"]]
    assert strongly_connected_components({}) == []


def test_self_loop_is_still_a_singleton():
    assert as_sets(strongly_connected_components({"A": ["A"]})) == frozenset(
        [frozenset({"A"})]
    )


def test_neighbour_only_node_is_included():
    # "B" is never a key, only a neighbour — it must still appear.
    assert as_sets(strongly_connected_components({"A": ["B"]})) == frozenset(
        [frozenset({"A"}), frozenset({"B"})]
    )


def test_disconnected_cycles_are_separate():
    graph = {
        "A": ["B"],
        "B": ["A"],
        "C": ["D"],
        "D": ["C"],
    }
    assert as_sets(strongly_connected_components(graph)) == frozenset(
        [frozenset({"A", "B"}), frozenset({"C", "D"})]
    )


def test_one_way_bridge_between_cycles():
    # {A, B} -> {C, D} one way: two components, never merged.
    graph = {"A": ["B", "C"], "B": ["A"], "C": ["D"], "D": ["C"]}
    assert as_sets(strongly_connected_components(graph)) == frozenset(
        [frozenset({"A", "B"}), frozenset({"C", "D"})]
    )


def test_duplicate_edges_do_not_break_it():
    graph = {"A": ["B", "B"], "B": ["A", "A"]}
    assert as_sets(strongly_connected_components(graph)) == frozenset(
        [frozenset({"A", "B"})]
    )


def test_is_strongly_connected():
    assert is_strongly_connected({"A": ["B"], "B": ["A"]}) is True
    assert is_strongly_connected({"A": ["B"], "B": []}) is False
    assert is_strongly_connected({}) is True
    assert is_strongly_connected({"A": []}) is True


def test_prerequisite_cycle_from_course_modules():
    # ARIN-1108 style: a circular prerequisite (DSA <-> Graphs) is one
    # component, while Logic feeding into it stays separate.
    graph = {
        "Logic": ["DSA"],
        "DSA": ["Graphs"],
        "Graphs": ["DSA"],
    }
    assert as_sets(strongly_connected_components(graph)) == frozenset(
        [frozenset({"Logic"}), frozenset({"DSA", "Graphs"})]
    )


def test_matches_brute_force_on_random_graphs():
    # Reachability both ways is the definition — check against it.
    rng = random.Random(7)
    for _ in range(30):
        n = rng.randint(2, 7)
        nodes = [chr(ord("A") + i) for i in range(n)]
        graph = {node: [] for node in nodes}
        for u in nodes:
            for v in nodes:
                if u != v and rng.random() < 0.3:
                    graph[u].append(v)

        def reaches(start, target):
            seen, stack = set(), [start]
            while stack:
                node = stack.pop()
                if node == target:
                    return True
                if node in seen:
                    continue
                seen.add(node)
                stack.extend(graph.get(node, ()))
            return False

        expected = set()
        for u in nodes:
            group = frozenset(
                v for v in nodes if reaches(u, v) and reaches(v, u)
            )
            expected.add(group)
        assert as_sets(strongly_connected_components(graph)) == frozenset(
            expected
        )
