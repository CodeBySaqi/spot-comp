"""0/1 knapsack (dynamic programming).

Classic ARIN-1108 dynamic-programming problem: given items with a
weight and a value each, pick a subset whose total weight fits in the
capacity and whose total value is as large as possible. Every item is
taken at most once — that is the "0/1" part, and it is what separates
this from the fractional knapsack, where a greedy take-the-best-ratio
first strategy works. Here greedy fails, so the table does the work:
``dp[i][w]`` is the best value using only the first ``i`` items with
capacity ``w``, and each item is either skipped (value from the row
above) or taken (its value plus the best value for the remaining
capacity using the items before it). Runs in O(n * capacity) time
and space, and the table also gives back which items were picked.
"""

from typing import List, Sequence, Tuple


def _validate(weights: Sequence[int], values: Sequence[int], capacity: int) -> None:
    """Reject the inputs the table cannot meaningfully handle."""
    if len(weights) != len(values):
        raise ValueError("weights and values must have the same length")
    if capacity < 0:
        raise ValueError("capacity must not be negative")
    if any(weight < 0 for weight in weights):
        raise ValueError("weights must not be negative")
    if any(value < 0 for value in values):
        raise ValueError("values must not be negative")


def _table(weights: Sequence[int], values: Sequence[int], capacity: int) -> List[List[int]]:
    """The DP table: ``dp[i][w]`` is the best value from the first ``i`` items."""
    rows = len(weights) + 1
    dp = [[0] * (capacity + 1) for _ in range(rows)]
    for i in range(1, rows):
        weight = weights[i - 1]
        value = values[i - 1]
        for w in range(capacity + 1):
            if weight > w:
                dp[i][w] = dp[i - 1][w]
            else:
                dp[i][w] = max(dp[i - 1][w], dp[i - 1][w - weight] + value)
    return dp


def knapsack(weights: Sequence[int], values: Sequence[int], capacity: int) -> int:
    """Return the maximum total value that fits in ``capacity``.

    Items are indexed in order: ``weights[i]`` and ``values[i]``
    describe the same item, and each item is taken at most once.
    """
    _validate(weights, values, capacity)
    if not weights:
        return 0
    return _table(weights, values, capacity)[-1][capacity]


def knapsack_items(weights: Sequence[int], values: Sequence[int], capacity: int) -> List[int]:
    """Return the indices of the items in one optimal packing.

    The indices come back in increasing order. When several packings
    tie for the best value, the one found by walking the table back
    from the last item is returned — it is optimal, just not
    necessarily the only one.
    """
    _validate(weights, values, capacity)
    if not weights:
        return []
    dp = _table(weights, values, capacity)
    chosen: List[int] = []
    w = capacity
    for i in range(len(weights), 0, -1):
        if dp[i][w] != dp[i - 1][w]:
            chosen.append(i - 1)
            w -= weights[i - 1]
    return sorted(chosen)


def knapsack_value_and_items(
    weights: Sequence[int], values: Sequence[int], capacity: int
) -> Tuple[int, List[int]]:
    """Return ``(max_value, chosen_indices)`` for one optimal packing."""
    items = knapsack_items(weights, values, capacity)
    return sum(values[i] for i in items), items
