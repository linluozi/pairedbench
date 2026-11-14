"""Tiny, dependency-free statistics for paired benchmark comparisons.

Everything here is deliberately transparent: no scipy, no numpy, no hidden
random state.  The bootstrap and the sign test use an explicit ``random.Random``
seed so that a report can be reproduced byte for byte.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist
from typing import Sequence

# 80% / 90% power quantiles, kept only as an allowed-value table.
Z_POWER = {0.8: 0.8416212335729143, 0.9: 1.2815515655446004}


def median(xs: Sequence[float]) -> float:
    """Median with the usual even-length average rule."""
    if not xs:
        raise ValueError("median() of an empty sequence")
    ordered = sorted(xs)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def percentile(xs: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile; ``q`` is in [0, 100]."""
    if not xs:
        raise ValueError("percentile() of an empty sequence")
    if not 0.0 <= q <= 100.0:
        raise ValueError("q must be within [0, 100]")
    ordered = sorted(xs)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def mean(xs: Sequence[float]) -> float:
    if not xs:
        raise ValueError("mean() of an empty sequence")
    return sum(xs) / len(xs)


def stdev(xs: Sequence[float]) -> float:
    """Sample standard deviation (n - 1); 0.0 for a single sample."""
    n = len(xs)
    if n < 2:
        return 0.0
    mu = mean(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))


def bootstrap_median_ci(
    xs: Sequence[float],
    resamples: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap CI for the median of ``xs``."""
    if not xs:
        raise ValueError("bootstrap_median_ci() of an empty sequence")
    if resamples < 1:
        raise ValueError("resamples must be >= 1")
    rng = random.Random(seed)
    n = len(xs)
    meds = []
    for _ in range(resamples):
        draw = [xs[rng.randrange(n)] for _ in range(n)]
        meds.append(median(draw))
    return percentile(meds, 100.0 * alpha / 2.0), percentile(
        meds, 100.0 * (1.0 - alpha / 2.0)
    )


def sign_test_p(ratios: Sequence[float]) -> float:
    """Exact two-sided sign test for H0: median(log ratio) == 0.

    Ties (ratio exactly 1.0) are dropped, which is the standard conservative
    treatment.  With n well under a few thousand the exact binomial tail is
    cheap enough to compute directly.
    """
    positive = sum(1 for r in ratios if r > 1.0)
    negative = sum(1 for r in ratios if r < 1.0)
    n = positive + negative
    if n == 0:
        return 1.0
    k = min(positive, negative)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / float(2**n)
    return min(1.0, 2.0 * tail)


def _ranks(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        average_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = average_rank
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Spearman rank correlation, ties averaged; 0.0 when undefined."""
    if len(xs) != len(ys):
        raise ValueError("spearman() needs equal-length sequences")
    n = len(xs)
    if n < 3:
        return 0.0
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0.0 or dy == 0.0:
        return 0.0
    return num / (dx * dy)


def minimum_detectable_effect(
    sigma_log: float, n_pairs: int, power: float = 0.8, alpha: float = 0.05
) -> float:
    """Approximate MDE on the log scale for a paired design.

    ``(z_{1-alpha/2} + z_power) * sigma / sqrt(n)`` -- the standard normal
    approximation.  It is a *planning* number, not a guarantee: it assumes the
    log-ratios are roughly normal and uses the observed sigma.
    """
    if n_pairs < 1:
        raise ValueError("n_pairs must be >= 1")
    if power not in Z_POWER:
        raise ValueError("power must be one of %s" % sorted(Z_POWER))
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be within (0, 1)")
    if sigma_log < 0.0:
        raise ValueError("sigma_log must be >= 0")
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1.0 - alpha / 2.0)
    z_power = normal.inv_cdf(power)
    return (z_alpha + z_power) * sigma_log / math.sqrt(n_pairs)
