"""Edit distance (Levenshtein distance, dynamic programming).

Classic ARIN-1108 dynamic-programming problem: the minimum number of
single-character edits — insert, delete, substitute — needed to turn
one sequence into another. It is the natural next step after the
longest common subsequence: where LCS only counts what two sequences
share, edit distance counts what it costs to make them identical, so
it is the workhorse behind spell checkers, DNA alignment and diff
tools. Here ``dp[i][j]`` is the edit distance between the first ``i``
elements of ``a`` and the first ``j`` of ``b``: matching characters
cost nothing over the diagonal cell, a substitution costs one over
the diagonal, and an insertion or deletion costs one over the cell
above or to the left. Runs in O(m * n) time and space, and walking
the table back from the corner reconstructs one cheapest edit script.
"""

from typing import List, Sequence, Tuple, TypeVar

T = TypeVar("T")

# One edit step: ("match", index, element), ("substitute", index,
# old, new), ("delete", index, element) or ("insert", index, element).
# Indexes refer to positions in the source sequence ``a`` as the
# script is applied left to right.
EditOp = Tuple[str, int, T, T]


def _table(a: Sequence[T], b: Sequence[T]) -> List[List[int]]:
    """The DP table: ``dp[i][j]`` is the edit distance of ``a[:i]`` and ``b[:j]``."""
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        dp[i][0] = i
    for j in range(len(b) + 1):
        dp[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j - 1] + cost,  # substitute (or match)
                dp[i - 1][j] + 1,  # delete a[i - 1]
                dp[i][j - 1] + 1,  # insert b[j - 1]
            )
    return dp


def edit_distance(a: Sequence[T], b: Sequence[T]) -> int:
    """Return the minimum number of edits to turn ``a`` into ``b``.

    Works on any sequences — strings, lists, tuples — as long as
    their elements support ``==``. Insert, delete and substitute
    each cost 1; a match costs 0.
    """
    if a == b:
        return 0
    return _table(a, b)[-1][-1]


def edit_operations(a: Sequence[T], b: Sequence[T]) -> List[EditOp]:
    """Return one cheapest edit script turning ``a`` into ``b``.

    Each step is a tuple: ``("match", i, element, element)``,
    ``("substitute", i, old, new)``, ``("delete", i, element, element)``
    or ``("insert", i, element, element)``. The steps are ordered left
    to right, so applying them to ``a`` yields ``b``. When several
    cheapest scripts exist, the one found by walking the table back
    from the corner is returned — it is cheapest, just not
    necessarily the only one.
    """
    dp = _table(a, b)
    ops: List[EditOp] = []
    i, j = len(a), len(b)
    while i > 0 or j > 0:
        if i > 0 and j > 0 and a[i - 1] == b[j - 1]:
            ops.append(("match", i - 1, a[i - 1], b[j - 1]))
            i -= 1
            j -= 1
        elif (
            i > 0
            and j > 0
            and dp[i][j] == dp[i - 1][j - 1] + 1
        ):
            ops.append(("substitute", i - 1, a[i - 1], b[j - 1]))
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("delete", i - 1, a[i - 1], a[i - 1]))
            i -= 1
        else:
            ops.append(("insert", i, b[j - 1], b[j - 1]))
            j -= 1
    ops.reverse()
    return ops


def edit_distance_and_operations(
    a: Sequence[T], b: Sequence[T]
) -> Tuple[int, List[EditOp]]:
    """Return ``(distance, one_cheapest_edit_script)`` of ``a`` and ``b``."""
    ops = edit_operations(a, b)
    distance = sum(1 for op in ops if op[0] != "match")
    return distance, ops
