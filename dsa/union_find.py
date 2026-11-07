"""Disjoint Set Union (Union-Find) with path compression and union by rank.

Classic ARIN-1108 data structure: maintains a partition of ``n`` elements
into disjoint sets with near-constant amortized operations. Used by
Kruskal's MST, connected-components and cycle detection.
"""


class UnionFind:
    """Union-Find over elements ``0 .. n-1``."""

    def __init__(self, n: int) -> None:
        if n < 0:
            raise ValueError("n must be non-negative")
        self._parent = list(range(n))
        self._rank = [0] * n
        self._size = [1] * n
        self._components = n

    def _check(self, x: int) -> None:
        if not 0 <= x < len(self._parent):
            raise IndexError(f"element {x} out of range")

    def find(self, x: int) -> int:
        """Return the representative of x's set (with path compression)."""
        self._check(x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # compress the whole path to the root
        while self._parent[x] != x:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> bool:
        """Merge the sets of a and b. Returns True if a merge happened."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        # union by rank: shorter tree goes under the taller one
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._size[ra] += self._size[rb]
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1
        self._components -= 1
        return True

    def connected(self, a: int, b: int) -> bool:
        """True if a and b are in the same set."""
        return self.find(a) == self.find(b)

    def component_size(self, x: int) -> int:
        """Number of elements in x's set."""
        return self._size[self.find(x)]

    @property
    def num_components(self) -> int:
        """Current number of disjoint sets."""
        return self._components

    def __len__(self) -> int:
        return len(self._parent)
