"""Longest common subsequence (dynamic programming).

Classic ARIN-1108 dynamic-programming problem: given two sequences,
find the longest sequence that appears as a subsequence of both —
the characters need not be adjacent, only in the same order. It is
the workhorse behind diff tools and DNA alignment, and it is a close
cousin of the 0/1 knapsack: both fill a table by deciding, cell by
cell, whether to take the current element or skip it. Here
``dp[i][j]`` is the LCS length of the first ``i`` elements of ``a``
and the first ``j`` of ``b``: when the two current elements match,
the answer grows by one over the diagonal cell; when they differ,
the best of dropping one element from either side wins. Runs in
O(m * n) time and space, and walking the table back from the corner
reconstructs one longest common subsequence.
"""

from typing import List, Sequence, Tuple, TypeVar

T = TypeVar("T")


def _table(a: Sequence[T], b: Sequence[T]) -> List[List[int]]:
    """The DP table: ``dp[i][j]`` is the LCS length of ``a[:i]`` and ``b[:j]``."""
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp


def lcs_length(a: Sequence[T], b: Sequence[T]) -> int:
    """Return the length of the longest common subsequence of ``a`` and ``b``.

    Works on any sequences — strings, lists, tuples — as long as
    their elements support ``==``.
    """
    if not a or not b:
        return 0
    return _table(a, b)[-1][-1]


def lcs(a: Sequence[T], b: Sequence[T]) -> Sequence[T]:
    """Return one longest common subsequence of ``a`` and ``b``.

    Returns the same type as ``a``: a string for strings, a list for
    lists and tuples. When several longest subsequences exist, the
    one found by walking the table back from the corner is returned
    — it is longest, just not necessarily the only one.
    """
    if not a or not b:
        return a[:0]
    dp = _table(a, b)
    picked: List[T] = []
    i, j = len(a), len(b)
    while i > 0 and j > 0:
        if a[i - 1] == b[j - 1]:
            picked.append(a[i - 1])
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    picked.reverse()
    result = picked
    if isinstance(a, str):
        return "".join(result)  # type: ignore[return-value]
    return result


def lcs_length_and_sequence(a: Sequence[T], b: Sequence[T]) -> Tuple[int, Sequence[T]]:
    """Return ``(length, one_longest_common_subsequence)`` of ``a`` and ``b``."""
    sequence = lcs(a, b)
    return len(sequence), sequence
