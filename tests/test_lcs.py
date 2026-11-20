import itertools
import random

import pytest

from dsa.lcs import lcs, lcs_length, lcs_length_and_sequence


def _is_subsequence(sub, seq):
    """Check ``sub`` appears in ``seq`` in order (not necessarily adjacent)."""
    it = iter(seq)
    return all(any(item == wanted for item in it) for wanted in sub)


def test_classic_example():
    # "ABCBDAB" vs "BDCABA": longest common subsequences have length 4,
    # e.g. "BCBA" and "BDAB".
    assert lcs_length("ABCBDAB", "BDCABA") == 4
    sequence = lcs("ABCBDAB", "BDCABA")
    assert len(sequence) == 4
    assert _is_subsequence(sequence, "ABCBDAB")
    assert _is_subsequence(sequence, "BDCABA")


def test_identical_sequences():
    assert lcs_length("AGGTAB", "AGGTAB") == 6
    assert lcs("AGGTAB", "AGGTAB") == "AGGTAB"
    assert lcs_length_and_sequence("AGGTAB", "AGGTAB") == (6, "AGGTAB")


def test_no_common_characters():
    assert lcs_length("ABC", "DEF") == 0
    assert lcs("ABC", "DEF") == ""
    assert lcs_length_and_sequence("ABC", "DEF") == (0, "")


def test_empty_inputs():
    assert lcs_length("", "ABC") == 0
    assert lcs_length("ABC", "") == 0
    assert lcs_length("", "") == 0
    assert lcs("", "ABC") == ""
    assert lcs("ABC", "") == ""


def test_single_character():
    assert lcs_length("A", "A") == 1
    assert lcs("A", "A") == "A"
    assert lcs_length("A", "B") == 0
    assert lcs_length("A", "BAC") == 1
    assert lcs("A", "BAC") == "A"


def test_one_is_subsequence_of_the_other():
    assert lcs_length("ACE", "ABCDE") == 3
    assert lcs("ACE", "ABCDE") == "ACE"
    assert lcs_length("ABCDE", "ACE") == 3
    assert lcs("ABCDE", "ACE") == "ACE"


def test_repeated_characters():
    # "AAAA" vs "AA": only two A's can line up.
    assert lcs_length("AAAA", "AA") == 2
    assert lcs("AAAA", "AA") == "AA"
    # "ABAB" vs "BABA": length 3, e.g. "ABA" or "BAB".
    assert lcs_length("ABAB", "BABA") == 3
    sequence = lcs("ABAB", "BABA")
    assert len(sequence) == 3
    assert _is_subsequence(sequence, "ABAB")
    assert _is_subsequence(sequence, "BABA")


def test_works_on_lists_not_just_strings():
    a = [1, 2, 3, 4, 1]
    b = [3, 4, 1, 2, 1, 3]
    assert lcs_length(a, b) == 3
    sequence = lcs(a, b)
    assert len(sequence) == 3
    assert _is_subsequence(sequence, a)
    assert _is_subsequence(sequence, b)
    length, seq = lcs_length_and_sequence(a, b)
    assert length == 3
    assert seq == sequence


def test_matches_brute_force_on_random_strings():
    # Exhaustive check: every subsequence of the shorter string,
    # keep the longest that is also a subsequence of the other.
    rng = random.Random(7)
    alphabet = "ABC"
    for _ in range(40):
        n = rng.randint(0, 7)
        m = rng.randint(0, 7)
        a = "".join(rng.choice(alphabet) for _ in range(n))
        b = "".join(rng.choice(alphabet) for _ in range(m))
        best = 0
        for r in range(n + 1):
            for combo in itertools.combinations(range(n), r):
                candidate = "".join(a[i] for i in combo)
                if _is_subsequence(candidate, b):
                    best = max(best, len(candidate))
        assert lcs_length(a, b) == best
        sequence = lcs(a, b)
        assert len(sequence) == best
        assert _is_subsequence(sequence, a)
        assert _is_subsequence(sequence, b)


def test_length_is_symmetric():
    rng = random.Random(21)
    for _ in range(20):
        a = "".join(rng.choice("ABCD") for _ in range(rng.randint(0, 12)))
        b = "".join(rng.choice("ABCD") for _ in range(rng.randint(0, 12)))
        assert lcs_length(a, b) == lcs_length(b, a)


def test_long_inputs_still_fast():
    # 200 characters each over a 4-letter alphabet: the table is
    # 201 x 201, and the answer must be a valid common subsequence.
    rng = random.Random(3)
    a = "".join(rng.choice("ACGT") for _ in range(200))
    b = "".join(rng.choice("ACGT") for _ in range(200))
    length = lcs_length(a, b)
    sequence = lcs(a, b)
    assert length == len(sequence)
    assert 0 < length <= 200
    assert _is_subsequence(sequence, a)
    assert _is_subsequence(sequence, b)
