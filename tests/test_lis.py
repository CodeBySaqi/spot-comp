import random
from itertools import combinations

import pytest

from dsa.lis import lis_length, longest_increasing_subsequence


def _is_increasing(sub):
    return all(sub[i] < sub[i + 1] for i in range(len(sub) - 1))


def _is_subsequence(sub, seq):
    it = iter(seq)
    return all(any(x == y for y in it) for x in sub)


def _brute_lis_length(seq):
    # Exhaustive check: the longest strictly increasing
    # subsequence, over every subsequence, shortest first.
    best = 0
    for r in range(len(seq) + 1):
        for combo in combinations(seq, r):
            if _is_increasing(combo):
                best = max(best, r)
    return best


def test_classic_examples():
    assert lis_length([10, 9, 2, 5, 3, 7, 101, 18]) == 4
    assert lis_length([0, 1, 0, 3, 2, 3]) == 4
    assert lis_length([7, 7, 7, 7, 7, 7, 7]) == 1
    assert lis_length([1, 3, 6, 7, 9, 4, 10, 5, 6]) == 6
    assert lis_length([3, 10, 2, 1, 20]) == 3


def test_empty_and_single_element():
    assert lis_length([]) == 0
    assert longest_increasing_subsequence([]) == []
    assert lis_length([42]) == 1
    assert longest_increasing_subsequence([42]) == [42]
    assert lis_length("a") == 1
    assert longest_increasing_subsequence("a") == ["a"]


def test_already_sorted():
    assert lis_length([1, 2, 3, 4, 5]) == 5
    assert longest_increasing_subsequence([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]
    assert lis_length(list(range(100))) == 100


def test_strictly_decreasing():
    assert lis_length([5, 4, 3, 2, 1]) == 1
    result = longest_increasing_subsequence([5, 4, 3, 2, 1])
    assert len(result) == 1
    assert result[0] in [5, 4, 3, 2, 1]


def test_equal_values_do_not_extend():
    # Strictly increasing: duplicates count once per run.
    assert lis_length([1, 2, 2, 3]) == 3
    assert lis_length([2, 2, 2, 3, 3, 4]) == 3
    assert lis_length([1, 1, 1, 1]) == 1


def test_reconstruction_is_valid():
    seq = [10, 9, 2, 5, 3, 7, 101, 18]
    result = longest_increasing_subsequence(seq)
    assert len(result) == lis_length(seq) == 4
    assert _is_increasing(result)
    assert _is_subsequence(result, seq)


def test_reconstruction_on_random_inputs():
    rng = random.Random(7)
    for _ in range(30):
        seq = [rng.randint(0, 9) for _ in range(rng.randint(0, 12))]
        result = longest_increasing_subsequence(seq)
        assert len(result) == lis_length(seq)
        assert _is_increasing(result)
        assert _is_subsequence(result, seq)


def test_works_on_strings_and_tuples():
    assert lis_length("bacd") == 3  # b < c < d, or a < c < d
    result = longest_increasing_subsequence("bacd")
    assert len(result) == 3
    assert _is_increasing(result)
    assert _is_subsequence(result, "bacd")
    assert lis_length((3, 1, 2)) == 2
    assert longest_increasing_subsequence((3, 1, 2)) == [1, 2]
    assert lis_length(["b", "a", "c"]) == 2


def test_negative_and_float_values():
    assert lis_length([-3, -1, -2, 0, 2, 1]) == 4
    assert lis_length([0.5, 1.5, 1.0, 2.5]) == 3


def test_matches_brute_force_on_random_inputs():
    rng = random.Random(4)
    for _ in range(40):
        seq = [rng.randint(0, 5) for _ in range(rng.randint(0, 9))]
        assert lis_length(seq) == _brute_lis_length(seq)
        result = longest_increasing_subsequence(seq)
        assert len(result) == _brute_lis_length(seq)
        assert _is_increasing(result)
        assert _is_subsequence(result, seq)


def test_long_inputs_still_fast():
    rng = random.Random(9)
    seq = [rng.randint(0, 10_000) for _ in range(5000)]
    length = lis_length(seq)
    result = longest_increasing_subsequence(seq)
    assert len(result) == length
    assert _is_increasing(result)
    assert _is_subsequence(result, seq)
    assert length > 50  # random data of this size has a long LIS


def test_no_element_reused():
    # Every element of the answer comes from a distinct position.
    seq = [2, 1, 2, 3, 2, 4]
    result = longest_increasing_subsequence(seq)
    assert len(result) == lis_length(seq) == 4
    assert result == [1, 2, 3, 4]
