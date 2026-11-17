import math
import random

import pytest

from dsa.astar import astar, astar_path
from dsa.dijkstra import dijkstra


# Same small graph as the Dijkstra tests:
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


def test_source_equals_target():
    path, cost = astar(GRAPH, "A", "A")
    assert path == ["A"]
    assert cost == 0


def test_shortest_path_matches_dijkstra_cost():
    # A->B->D->F costs 1 + 2 + 1 = 4, same as Dijkstra's distance.
    path, cost = astar(GRAPH, "A", "F")
    assert path == ["A", "B", "D", "F"]
    assert cost == 4
    distances, _ = dijkstra(GRAPH, "A")
    assert cost == distances["F"]


def test_zero_heuristic_is_dijkstra():
    # A zero heuristic makes A* expand like Dijkstra's and agree on
    # every target.
    distances, _ = dijkstra(GRAPH, "A")
    for target, expected in distances.items():
        _, cost = astar(GRAPH, "A", target, heuristic=lambda _n, _t: 0)
        assert cost == expected


def test_admissible_heuristic_still_optimal():
    # Underestimate the remaining cost (never overestimate) and A*
    # must still find the optimal path, here A->B->E = 2.
    def underestimate(node, target):
        return 0.5 if node != target else 0

    path, cost = astar(GRAPH, "A", "E", heuristic=underestimate)
    assert path == ["A", "B", "E"]
    assert cost == 2


def test_grid_with_manhattan_heuristic():
    # 4x4 grid, moving up/down/left/right costs 1. Manhattan distance
    # to the goal is admissible, so A* finds a shortest path of 6.
    def neighbours(cell):
        x, y = cell
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < 4 and 0 <= ny < 4:
                yield (nx, ny), 1

    grid = {cell: list(neighbours(cell)) for cell in
            ((x, y) for x in range(4) for y in range(4))}
    manhattan = lambda cell, goal: abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])
    path, cost = astar(grid, (0, 0), (3, 3), heuristic=manhattan)
    assert cost == 6
    assert len(path) == 7
    assert path[0] == (0, 0) and path[-1] == (3, 3)


def test_obstacle_forces_a_detour():
    # 3x3 grid with the middle row blocked except at the far right;
    # the only way through is around the wall.
    blocked = {(1, 0), (1, 1)}
    grid = {}
    for x in range(3):
        for y in range(3):
            if (x, y) in blocked:
                continue
            edges = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (x + dx, y + dy)
                if 0 <= nxt[0] < 3 and 0 <= nxt[1] < 3 and nxt not in blocked:
                    edges.append((nxt, 1))
            grid[(x, y)] = edges
    manhattan = lambda cell, goal: abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])
    path, cost = astar(grid, (0, 0), (2, 2), heuristic=manhattan)
    assert cost == 4
    assert path == [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)]


def test_unreachable_target():
    graph = {"A": [("B", 1)], "B": [], "C": []}
    path, cost = astar(graph, "A", "C")
    assert path == []
    assert cost == math.inf
    assert astar_path(graph, "A", "C") == []


def test_unknown_target_is_unreachable_not_an_error():
    path, cost = astar(GRAPH, "A", "Z")
    assert path == []
    assert cost == math.inf


def test_neighbour_only_target_is_reachable():
    # "T" appears only as a neighbour, never as a key — still found.
    graph = {"A": [("T", 5)]}
    path, cost = astar(graph, "A", "T")
    assert path == ["A", "T"]
    assert cost == 5


def test_unknown_source_raises():
    with pytest.raises(KeyError):
        astar(GRAPH, "Z", "A")


def test_negative_weight_raises():
    graph = {"A": [("B", -1)], "B": []}
    with pytest.raises(ValueError, match="negative edge weight"):
        astar(graph, "A", "B")


def test_single_node_graph():
    path, cost = astar({"A": []}, "A", "A")
    assert path == ["A"]
    assert cost == 0


def test_zero_weight_edges_work():
    graph = {"A": [("B", 0)], "B": [("C", 0)], "C": []}
    path, cost = astar(graph, "A", "C")
    assert path == ["A", "B", "C"]
    assert cost == 0


def test_directed_graph_respects_direction():
    # One-way street: A -> B exists, B -> A does not.
    graph = {"A": [("B", 1)], "B": [("C", 1)], "C": []}
    assert astar_path(graph, "A", "C") == ["A", "B", "C"]
    assert astar_path(graph, "C", "A") == []


def test_random_graphs_match_dijkstra():
    # 30 random small graphs: with a zero heuristic A* must agree
    # with Dijkstra on every reachable target's cost.
    rng = random.Random(7)
    for _ in range(30):
        nodes = [f"n{i}" for i in range(6)]
        graph = {n: [] for n in nodes}
        for u in nodes:
            for v in rng.sample(nodes, 2):
                if u != v:
                    graph[u].append((v, rng.randint(1, 9)))
        distances, _ = dijkstra(graph, "n0")
        for target, expected in distances.items():
            _, cost = astar(graph, "n0", target)
            assert cost == expected
