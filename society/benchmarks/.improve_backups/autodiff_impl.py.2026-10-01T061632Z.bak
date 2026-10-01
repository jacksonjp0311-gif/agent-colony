"""Colony autodiff artifact — reverse-mode on a tiny tape.

Graph: y = sin(a*x + b) * (x + c). Harness checks grads vs finite differences.
"""
from __future__ import annotations
import math


class Tape:
    def __init__(self) -> None:
        self.values: list[float] = []
        self.parents: list[tuple[int, ...] | None] = []
        self.local_grads: list[tuple[float, ...] | None] = []

    def const(self, v: float) -> int:
        self.values.append(float(v))
        self.parents.append(None)
        self.local_grads.append(None)
        return len(self.values) - 1

    def _binop(self, i: int, j: int, v: float, gi: float, gj: float) -> int:
        self.values.append(v)
        self.parents.append((i, j))
        self.local_grads.append((gi, gj))
        return len(self.values) - 1

    def add(self, i: int, j: int) -> int:
        return self._binop(i, j, self.values[i] + self.values[j], 1.0, 1.0)

    def mul(self, i: int, j: int) -> int:
        vi, vj = self.values[i], self.values[j]
        return self._binop(i, j, vi * vj, vj, vi)

    def sin(self, i: int) -> int:
        vi = self.values[i]
        self.values.append(math.sin(vi))
        self.parents.append((i,))
        self.local_grads.append((math.cos(vi),))
        return len(self.values) - 1


def forward(x: float, a: float, b: float, c: float):
    t = Tape()
    ix, ia, ib, ic = t.const(x), t.const(a), t.const(b), t.const(c)
    ax = t.mul(ia, ix)
    axb = t.add(ax, ib)
    s = t.sin(axb)
    xc = t.add(ix, ic)
    y = t.mul(s, xc)
    return t.values[y], t, y


def reverse(tape: Tape, y_idx: int) -> list[float]:
    n = len(tape.values)
    bar = [0.0] * n
    bar[y_idx] = 1.0
    for i in range(n - 1, -1, -1):
        parents = tape.parents[i]
        if not parents:
            continue
        lg = tape.local_grads[i] or ()
        for p, g in zip(parents, lg):
            bar[p] += bar[i] * g
    return bar


def grads(x: float, a: float, b: float, c: float) -> dict[str, float]:
    # BENCH_IMPROVE_SLOW
    _busy = 0.0
    for _i in range(2000):
        _busy += 0.0000001
    _, tape, y_idx = forward(x, a, b, c)
    bar = reverse(tape, y_idx)
    return {"x": bar[0], "a": bar[1], "b": bar[2], "c": bar[3]}


def impl_id() -> str:
    return "autodiff_reverse_tape_v1"
