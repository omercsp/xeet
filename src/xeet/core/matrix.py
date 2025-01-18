from collections.abc import Iterator
from typing import Any

MatrixType = dict[str, list[Any]]


class Matrix:
    def __init__(self, values: MatrixType) -> None:
        self.values = values
        self.lengths = {key: len(value) for key, value in self.values.items()}
        self.keys = sorted(list(self.values.keys()))
        self.n = len(self.keys)

    def permutations(self) -> Iterator[dict[str, Any]]:
        if self.n == 0:
            yield {}
            return
        for indices in self._permutation():
            yield {self.keys[i]: self.values[self.keys[i]][indices[i]] for i in range(self.n)}

    def _permutation(self, indices: list[int] = list(), i: int = -1) -> Iterator[list[int]]:
        if i == -1:
            indices = [0] * self.n
            i = 0
        for v in range(self.lengths[self.keys[i]]):
            indices[i] = v
            if i == self.n - 1:
                yield indices
            else:
                yield from self._permutation(indices, i + 1)
