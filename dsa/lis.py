"""Longest increasing subsequence (patience sorting, O(n log n)).

Classic ARIN-1108 dynamic-programming problem: the longest
subsequence of a sequence whose elements are strictly increasing.
It is the natural next step after the longest common subsequence
and edit distance: where LCS compares two sequences, LIS asks what
the single longest ordered pattern inside one sequence is, so it
is the workhorse behind diff tools, patience diff, and finding
the longest chain of compatible events. The naive DP keeps, for
each position, the best length ending there and runs in O(n * n);
the patience-sorting version here keeps, for each length ``k``,
the smallest possible tail value of an increasing subsequence of
that length. Each new element either extends the longest pile
or replaces the tail of the first pile it fits under (found with
binary search, hence O(n log n)), and predecessor links recorded
along the way reconstruct one longest subsequence.
"""

from bisect import bisect_left
from typing import List, Sequence, TypeVar

T = TypeVar("T")


def _patience(seq: Sequence[T]):
    """Patience piles for ``seq``: tails and predecessor links.

    Returns ``(tails, prev, best)`` where ``tails[k]`` is the index
    of the smallest possible tail of an increasing subsequence of
    length ``k + 1``, ``prev[i]`` is the index of the element before
    ``seq[i]`` in such a subsequence (or -1), and ``best`` is the
    index of the tail of one longest subsequence.
    """
    tails: List[int] = []
    tail_values: List[T] = []
    prev: List[int] = []
    for i, value in enumerate(seq):
        # First pile whose tail is >= value: that pile's tail can be
        # replaced by value without breaking the increasing order.
        # bisect_left (not bisect_right) keeps the subsequence
        # strictly increasing, so equal values never extend a pile.
        pos = bisect_left(tail_values, value)
        prev.append(tails[pos - 1] if pos > 0 else -1)
        if pos == len(tails):
            tails.append(i)
            tail_values.append(value)
        else:
            tails[pos] = i
            tail_values[pos] = value
    best = tails[-1] if tails else -1
    return tails, prev, best


def lis_length(seq: Sequence[T]) -> int:
    """Return the length of the longest increasing subsequence.

    Works on any sequence of comparable elements — numbers, strings,
    tuples. The subsequence must be strictly increasing, so equal
    values do not extend it: ``lis_length([7, 7, 7])`` is 1.
    """
    tails, _prev, _best = _patience(seq)
    return len(tails)


def longest_increasing_subsequence(seq: Sequence[T]) -> List[T]:
    """Return one longest increasing subsequence of ``seq``.

    The result is a list of elements from ``seq``, in order, strictly
    increasing, and as long as any such subsequence. When several
    longest subsequences exist, the one found by the patience piles
    is returned — it is longest, just not necessarily the only one.
    """
    _tails, prev, best = _patience(seq)
    out: List[T] = []
    while best != -1:
        out.append(seq[best])
        best = prev[best]
    out.reverse()
    return out
