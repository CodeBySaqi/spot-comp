import itertools
import random

import pytest

from dsa.knapsack import knapsack, knapsack_items, knapsack_value_and_items


def test_classic_example():
    # weights [1, 3, 4, 5], values [1, 4, 5, 7], capacity 7:
    # items 1 + 2 (3 + 4) give 4 + 5 = 9, the best packing.
    assert knapsack([1, 3, 4, 5], [1, 4, 5, 7], 7) == 9
    assert knapsack_items([1, 3, 4, 5], [1, 4, 5, 7], 7) == [1, 2]


def test_empty_items_and_zero_capacity():
    assert knapsack([], [], 10) == 0
    assert knapsack_items([], [], 10) == []
    assert knapsack([2, 3], [5, 6], 0) == 0
    assert knapsack_items([2, 3], [5, 6], 0) == []


def test_nothing_fits():
    assert knapsack([5, 6], [10, 12], 4) == 0
    assert knapsack_items([5, 6], [10, 12], 4) == []


def test_everything_fits():
    assert knapsack([1, 2, 3], [10, 20, 30], 10) == 60
    assert knapsack_items([1, 2, 3], [10, 20, 30], 10) == [0, 1, 2]


def test_single_item_fits_or_not():
    assert knapsack([4], [9], 4) == 9
    assert knapsack_items([4], [9], 4) == [0]
    assert knapsack([5], [9], 4) == 0
    assert knapsack_items([5], [9], 4) == []


def test_same_weight_picks_higher_value():
    # Two items weigh 3, capacity 3: the 8-value one wins over the 5.
    assert knapsack([3, 3], [5, 8], 3) == 8
    assert knapsack_items([3, 3], [5, 8], 3) == [1]


def test_zero_weight_item_is_always_taken():
    assert knapsack([0, 3], [7, 5], 3) == 12
    assert knapsack_items([0, 3], [7, 5], 3) == [0, 1]


def test_greedy_by_ratio_fails_here():
    # Best value-per-weight first takes the 60, then the 100 (cap 50
    # leaves no room for the 120) for 160. The optimum is 220:
    # the 100 and the 120 together, exactly filling the capacity.
    assert knapsack([10, 20, 30], [60, 100, 120], 50) == 220
    assert knapsack_items([10, 20, 30], [60, 100, 120], 50) == [1, 2]


def test_chosen_items_add_up_to_the_value():
    weights = [2, 3, 4, 5, 9]
    values = [3, 4, 5, 8, 10]
    capacity = 11
    value, items = knapsack_value_and_items(weights, values, capacity)
    assert value == knapsack(weights, values, capacity) == 16
    assert sum(weights[i] for i in items) <= capacity
    assert sum(values[i] for i in items) == value
    assert items == sorted(items)


def test_repeated_weights_and_values():
    # Five identical items, capacity for exactly three of them.
    assert knapsack([2] * 5, [3] * 5, 6) == 9
    assert len(knapsack_items([2] * 5, [3] * 5, 6)) == 3


def test_matches_brute_force_on_random_inputs():
    # Exhaustive check: every subset, keep the best that fits.
    rng = random.Random(11)
    for _ in range(40):
        n = rng.randint(0, 8)
        weights = [rng.randint(0, 6) for _ in range(n)]
        values = [rng.randint(0, 10) for _ in range(n)]
        capacity = rng.randint(0, 12)
        best = 0
        for r in range(n + 1):
            for combo in itertools.combinations(range(n), r):
                if sum(weights[i] for i in combo) <= capacity:
                    best = max(best, sum(values[i] for i in combo))
        assert knapsack(weights, values, capacity) == best
        items = knapsack_items(weights, values, capacity)
        assert sum(weights[i] for i in items) <= capacity
        assert sum(values[i] for i in items) == best


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        knapsack([1, 2], [5], 5)
    with pytest.raises(ValueError):
        knapsack_items([1], [5, 6], 5)


def test_negative_inputs_raise():
    with pytest.raises(ValueError):
        knapsack([1, -2], [5, 6], 5)
    with pytest.raises(ValueError):
        knapsack([1, 2], [5, -6], 5)
    with pytest.raises(ValueError):
        knapsack([1, 2], [5, 6], -1)


def test_many_items_still_fast_and_correct():
    # 100 items, weights 1..100, values 2x weight: best is to fill
    # the capacity exactly, value 2 * capacity.
    weights = list(range(1, 101))
    values = [2 * w for w in weights]
    assert knapsack(weights, values, 50) == 100
    items = knapsack_items(weights, values, 50)
    assert sum(weights[i] for i in items) == 50
    assert sum(values[i] for i in items) == 100
