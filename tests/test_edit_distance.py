import random

import pytest

from dsa.edit_distance import (
    edit_distance,
    edit_distance_and_operations,
    edit_operations,
)


def _apply_ops(a, ops):
    """Apply an edit script to ``a`` and return the resulting sequence."""
    out = []
    cursor = 0
    for kind, _index, old, new in ops:
        if kind == "match":
            assert a[cursor] == old
            out.append(old)
            cursor += 1
        elif kind == "substitute":
            assert a[cursor] == old
            out.append(new)
            cursor += 1
        elif kind == "delete":
            assert a[cursor] == old
            cursor += 1
        elif kind == "insert":
            out.append(new)
        else:  # pragma: no cover - the module only emits these four kinds
            raise AssertionError(kind)
    assert cursor == len(a)
    return "".join(out) if isinstance(a, str) else out


def _edits_in(ops):
    return sum(1 for op in ops if op[0] != "match")


def test_classic_examples():
    # "kitten" -> "sitting": substitute k->s, e->i, insert g = 3.
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("flaw", "lawn") == 2
    assert edit_distance("sunday", "saturday") == 3
    assert edit_distance("gumbo", "gambol") == 2
    assert edit_distance("horse", "ros") == 3
    assert edit_distance("intention", "execution") == 5


def test_identical_sequences():
    assert edit_distance("AGGTAB", "AGGTAB") == 0
    assert edit_operations("AGGTAB", "AGGTAB") == [
        ("match", i, ch, ch) for i, ch in enumerate("AGGTAB")
    ]
    assert edit_distance_and_operations("AGGTAB", "AGGTAB") == (
        0,
        [("match", i, ch, ch) for i, ch in enumerate("AGGTAB")],
    )


def test_empty_inputs():
    assert edit_distance("", "abc") == 3
    assert edit_distance("abc", "") == 3
    assert edit_distance("", "") == 0
    assert edit_operations("", "abc") == [
        ("insert", 0, "a", "a"),
        ("insert", 0, "b", "b"),
        ("insert", 0, "c", "c"),
    ]
    assert edit_operations("abc", "") == [
        ("delete", 0, "a", "a"),
        ("delete", 1, "b", "b"),
        ("delete", 2, "c", "c"),
    ]


def test_single_character():
    assert edit_distance("A", "A") == 0
    assert edit_distance("A", "B") == 1
    assert edit_distance("A", "BAC") == 2
    assert edit_distance("BAC", "A") == 2


def test_one_insertion_or_deletion():
    assert edit_distance("abc", "abxc") == 1
    assert edit_distance("abxc", "abc") == 1
    assert edit_distance("abc", "abcd") == 1
    assert edit_distance("abcd", "abc") == 1


def test_pure_substitutions():
    # Same length, every character differs: one substitution each.
    assert edit_distance("abc", "def") == 3
    assert edit_distance("aaa", "bbb") == 3


def test_operations_transform_source_into_target():
    for a, b in [
        ("kitten", "sitting"),
        ("flaw", "lawn"),
        ("sunday", "saturday"),
        ("intention", "execution"),
        ("", "abc"),
        ("abc", ""),
        ("AGGTAB", "AGGTAB"),
    ]:
        ops = edit_operations(a, b)
        assert _apply_ops(a, ops) == b
        assert _edits_in(ops) == edit_distance(a, b)
        distance, ops2 = edit_distance_and_operations(a, b)
        assert distance == edit_distance(a, b)
        assert ops2 == ops


def test_works_on_lists_not_just_strings():
    a = [1, 2, 3]
    b = [1, 4, 3, 5]
    assert edit_distance(a, b) == 2
    ops = edit_operations(a, b)
    assert _apply_ops(a, ops) == b
    assert _edits_in(ops) == 2


def test_distance_is_symmetric():
    rng = random.Random(11)
    for _ in range(20):
        a = "".join(rng.choice("ABCD") for _ in range(rng.randint(0, 10)))
        b = "".join(rng.choice("ABCD") for _ in range(rng.randint(0, 10)))
        assert edit_distance(a, b) == edit_distance(b, a)


def test_matches_brute_force_on_random_strings():
    # Exhaustive check on short strings: try every way of aligning
    # them with inserts/deletes/substitutes via the classic
    # recursive definition, and compare against the DP table.
    rng = random.Random(5)
    alphabet = "ABC"

    def brute(a, b):
        if not a:
            return len(b)
        if not b:
            return len(a)
        cost = 0 if a[0] == b[0] else 1
        return min(
            brute(a[1:], b[1:]) + cost,
            brute(a[1:], b) + 1,
            brute(a, b[1:]) + 1,
        )

    for _ in range(30):
        a = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 6)))
        b = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 6)))
        assert edit_distance(a, b) == brute(a, b)
        ops = edit_operations(a, b)
        assert _apply_ops(a, ops) == b
        assert _edits_in(ops) == edit_distance(a, b)


def test_triangle_inequality():
    rng = random.Random(17)
    for _ in range(20):
        a = "".join(rng.choice("ABCD") for _ in range(rng.randint(0, 8)))
        b = "".join(rng.choice("ABCD") for _ in range(rng.randint(0, 8)))
        c = "".join(rng.choice("ABCD") for _ in range(rng.randint(0, 8)))
        assert edit_distance(a, c) <= edit_distance(a, b) + edit_distance(b, c)


def test_long_inputs_still_fast():
    rng = random.Random(3)
    a = "".join(rng.choice("ACGT") for _ in range(200))
    b = "".join(rng.choice("ACGT") for _ in range(200))
    distance = edit_distance(a, b)
    ops = edit_operations(a, b)
    assert _apply_ops(a, ops) == b
    assert _edits_in(ops) == distance
    assert 0 < distance <= 200
