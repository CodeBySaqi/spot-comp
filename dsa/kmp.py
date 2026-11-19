"""Knuth-Morris-Pratt string search.

Classic ARIN-1108 string-matching problem: find every occurrence of a
pattern inside a text. The naive scan re-checks characters it has
already matched whenever a mismatch happens, which costs O(n * m) in
the worst case. KMP avoids that by precomputing, for the pattern, the
longest proper prefix that is also a suffix (the "lps" table) for every
prefix length. After a mismatch the table says exactly how far the
pattern can slide forward without re-checking characters that are
already known to match, so the whole search runs in O(n + m) time.
"""

from typing import List


def build_lps(pattern: str) -> List[int]:
    """Longest proper prefix that is also a suffix, for each prefix.

    ``lps[i]`` is the length of the longest proper prefix of
    ``pattern[:i + 1]`` that is also a suffix of it. A proper prefix
    is shorter than the string itself, so ``lps[i] < i + 1`` always.
    """
    lps = [0] * len(pattern)
    length = 0  # length of the previous longest prefix-suffix
    i = 1
    while i < len(pattern):
        if pattern[i] == pattern[length]:
            length += 1
            lps[i] = length
            i += 1
        elif length:
            length = lps[length - 1]
        else:
            lps[i] = 0
            i += 1
    return lps


def kmp_search(text: str, pattern: str) -> List[int]:
    """Return the start index of every occurrence of ``pattern`` in ``text``.

    Overlapping occurrences are all reported. An empty pattern matches
    at every position, including the one past the last character.
    """
    if not pattern:
        return list(range(len(text) + 1))
    lps = build_lps(pattern)
    matches: List[int] = []
    i = 0  # index into text
    j = 0  # index into pattern
    while i < len(text):
        if text[i] == pattern[j]:
            i += 1
            j += 1
            if j == len(pattern):
                matches.append(i - j)
                j = lps[j - 1]
        elif j:
            j = lps[j - 1]
        else:
            i += 1
    return matches


def kmp_contains(text: str, pattern: str) -> bool:
    """Return True if ``pattern`` occurs anywhere in ``text``."""
    return bool(kmp_search(text, pattern))
