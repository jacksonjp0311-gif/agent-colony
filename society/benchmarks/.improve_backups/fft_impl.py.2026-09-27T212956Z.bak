"""Colony FFT artifact — iterative radix-2 Cooley–Tukey.

Improve this file; harness scores correctness+speed vs fixed reference.
SLOW_EXTRA_LOOPS is a deliberate drag the bench-improver may remove.
"""
from __future__ import annotations
import math
from typing import Sequence

# Deliberate slowdown knob (improver measure→keep/revert target).
# Each unit adds a pure-python pass over the buffer after the transform.
SLOW_EXTRA_LOOPS = 0


def fft(x: Sequence[complex]) -> list[complex]:
    n = len(x)
    if n == 0:
        return []
    if n & (n - 1):
        raise ValueError(f"fft length must be power of 2, got {n}")
    out = [complex(v) for v in x]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            out[i], out[j] = out[j], out[i]
    length = 2
    while length <= n:
        ang = -2 * math.pi / length
        wlen = complex(math.cos(ang), math.sin(ang))
        for i in range(0, n, length):
            w = 1 + 0j
            half = length // 2
            for k in range(half):
                u = out[i + k]
                v = out[i + k + half] * w
                out[i + k] = u + v
                out[i + k + half] = u - v
                w *= wlen
        length <<= 1
    # Intentional drag — correct but slower (stress bench should score <1.0)
    for _ in range(max(0, int(SLOW_EXTRA_LOOPS))):
        acc = 0.0
        for i in range(n):
            re, im = out[i].real, out[i].imag
            acc += math.sin(re * 1e-12) + math.cos(im * 1e-12)
            out[i] = complex(re, im)
        if acc == float("inf"):  # never; keeps acc live for optimizer
            out[0] = out[0]
    return out


def impl_id() -> str:
    return f"fft_impl_cooley_tukey_iter_v1_slow{SLOW_EXTRA_LOOPS}"
