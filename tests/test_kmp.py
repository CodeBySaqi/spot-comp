import random

import pytest

from dsa.kmp import build_lps, kmp_contains, kmp_search


def naive_search(text, pattern):
    """Reference implementation: every start index, checked by hand."""
    if not pattern:
        return list(range(len(text) + 1))
    return [
        i
        for i in range(len(text) - len(pattern) + 1)
        if text[i : i + len(pattern)] == pattern
    ]


def test_classic_example():
    # "ABABCABAB" occurs in "ABABDABACDABABCABAB" at index 10.
    assert kmp_search("ABABDABACDABABCABAB", "ABABCABAB") == [10]


def test_overlapping_matches_all_reported():
    assert kmp_search("AAAAA", "AA") == [0, 1, 2, 3]
    assert kmp_search("ABABABA", "ABA") == [0, 2, 4]


def test_no_match():
    assert kmp_search("hello world", "xyz") == []
    assert kmp_search("abc", "abcd") == []


def test_empty_pattern_matches_everywhere():
    assert kmp_search("abc", "") == [0, 1, 2, 3]
    assert kmp_search("", "") == [0]


def test_empty_text():
    assert kmp_search("", "a") == []
    assert kmp_search("", "") == [0]


def test_pattern_equals_text():
    assert kmp_search("abc", "abc") == [0]


def test_single_character_pattern():
    assert kmp_search("banana", "a") == [1, 3, 5]


def test_repeated_prefix_pattern():
    # The lps table is what saves the re-checks here: "AABAAB" has
    # the prefix "AAB" repeating, and the match sits at index 6.
    assert kmp_search("AABAACAADAABAABA", "AABA") == [0, 9, 12]


def test_lps_table_values():
    assert build_lps("AAAA") == [0, 1, 2, 3]
    assert build_lps("ABCDE") == [0, 0, 0, 0, 0]
    assert build_lps("AABAACAABAA") == [0, 1, 0, 1, 2, 0, 1, 2, 3, 4, 5]
    assert build_lps("AAACAAAAAC") == [0, 1, 2, 0, 1, 2, 3, 3, 3, 4]
    assert build_lps("") == []


def test_matches_naive_on_random_texts():
    rng = random.Random(7)
    alphabet = "AB"
    for _ in range(60):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
        pattern = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 6)))
        assert kmp_search(text, pattern) == naive_search(text, pattern)


def test_matches_naive_on_random_words():
    rng = random.Random(21)
    words = ["the", "quick", "brown", "fox", "a", "an", "the"]
    for _ in range(30):
        text = " ".join(rng.choice(words) for _ in range(rng.randint(0, 8)))
        pattern = rng.choice(words + ["zzz", "quick brown"])
        assert kmp_search(text, pattern) == naive_search(text, pattern)


def test_kmp_contains():
    assert kmp_contains("hello world", "world")
    assert not kmp_contains("hello world", "mars")
    assert kmp_contains("abc", "")
