"""Interleaved paired A/B comparison with an explicit verdict."""

from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, dataclass
from typing import Callable, Sequence

from . import stats

DEFAULT_THRESHOLD = 1.02
DEFAULT_ALPHA = 0.05
DEFAULT_RESAMPLES = 2000
DEFAULT_DRIFT_THRESHOLD = 0.6


@dataclass(frozen=True)
class Comparison:
    """Result of one A/B comparison.

    ``speedup`` is ``median(a_i / b_i)``: values above 1 mean B was faster.
    The confidence interval always refers to that same statistic.
    """

    speedup: float
    ci_low: float
    ci_high: float
    p_value: float | None
    n_pairs: int
    median_a: float
    median_b: float
    sigma_log: float
    mde: float
    drift_rho: float
    drift_flagged: bool
    order_effect: float
    threshold: float
    method: str
    verdict: str

    def as_dict(self) -> dict:
        return asdict(self)


def analyze(
    a_times: Sequence[float],
    b_times: Sequence[float],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    alpha: float = DEFAULT_ALPHA,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
    paired: bool = True,
    drift_threshold: float = DEFAULT_DRIFT_THRESHOLD,
    order_flags: Sequence[bool] | None = None,
) -> Comparison:
    """Turn paired timing samples into a decision.

    ``order_flags[i]`` should be True when A ran first in pair ``i``; it is only
    used to report a rough order-effect diagnostic.
    """
    if len(a_times) != len(b_times):
        raise ValueError("a_times and b_times must have the same length")
    n = len(a_times)
    if n < 3:
        raise ValueError("need at least 3 pairs for a verdict")
    if any(t <= 0.0 for t in list(a_times) + list(b_times)):
        raise ValueError("timings must be strictly positive")
    if threshold <= 1.0:
        raise ValueError("threshold must be > 1.0")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be within (0, 1)")

    ratios = [a / b for a, b in zip(a_times, b_times)]
    log_ratios = [math.log(r) for r in ratios]
    sigma_log = stats.stdev(log_ratios)
    speedup = stats.median(ratios)

    if paired:
        ci_low, ci_high = stats.bootstrap_median_ci(
            ratios, resamples=resamples, alpha=alpha, seed=seed
        )
        p_value: float | None = stats.sign_test_p(ratios)
    else:
        # Independent resampling of each side: this is what a naive
        # "two separate benchmark runs" analysis does, and it throws away the
        # pairing.  We expose it so the calibration table can quantify the cost.
        rng = random.Random(seed + 17)
        boot = []
        for _ in range(resamples):
            draw_a = [a_times[rng.randrange(n)] for _ in range(n)]
            draw_b = [b_times[rng.randrange(n)] for _ in range(n)]
            boot.append(stats.median(draw_a) / stats.median(draw_b))
        ci_low = stats.percentile(boot, 100.0 * alpha / 2.0)
        ci_high = stats.percentile(boot, 100.0 * (1.0 - alpha / 2.0))
        p_value = None

    drift_rho = stats.spearman(
        list(range(n)), [a + b for a, b in zip(a_times, b_times)]
    )
    drift_flagged = n >= 8 and abs(drift_rho) >= drift_threshold

    if order_flags is not None and len(order_flags) == n:
        a_first = [r for r, flag in zip(ratios, order_flags) if flag]
        b_first = [r for r, flag in zip(ratios, order_flags) if not flag]
        if a_first and b_first:
            order_effect = stats.median(a_first) / stats.median(b_first)
        else:
            order_effect = 1.0
    else:
        order_effect = 1.0

    if ci_low >= threshold:
        verdict = "b_faster"
    elif ci_high <= 1.0 / threshold:
        verdict = "a_faster"
    else:
        verdict = "inconclusive"

    return Comparison(
        speedup=speedup,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=p_value,
        n_pairs=n,
        median_a=stats.median(a_times),
        median_b=stats.median(b_times),
        sigma_log=sigma_log,
        mde=stats.minimum_detectable_effect(sigma_log, n, power=0.8, alpha=alpha),
        drift_rho=drift_rho,
        drift_flagged=drift_flagged,
        order_effect=order_effect,
        threshold=threshold,
        method="paired" if paired else "unpaired",
        verdict=verdict,
    )


def ab_compare(
    fn_a: Callable[[], object],
    fn_b: Callable[[], object],
    *,
    samples: int = 21,
    warmup: int = 3,
    seed: int = 20261115,
    timer: Callable[[], float] = time.perf_counter,
    **analyze_kwargs,
) -> Comparison:
    """Run B against A with interleaved samples and a randomised order.

    Interleaving means a slow drift in machine load hits both sides roughly
    equally; randomising the within-pair order stops a fixed cache/allocator
    advantage from always landing on the same implementation.
    """
    if samples < 3:
        raise ValueError("samples must be >= 3")
    for _ in range(warmup):
        fn_a()
        fn_b()

    rng = random.Random(seed)
    a_times: list[float] = []
    b_times: list[float] = []
    order_flags: list[bool] = []
    for _ in range(samples):
        a_first = rng.random() < 0.5
        if a_first:
            t0 = timer()
            fn_a()
            t1 = timer()
            t2 = timer()
            fn_b()
            t3 = timer()
            a_time, b_time = t1 - t0, t3 - t2
        else:
            t0 = timer()
            fn_b()
            t1 = timer()
            t2 = timer()
            fn_a()
            t3 = timer()
            # The windows are swapped here on purpose: the first window is B.
            a_time, b_time = t3 - t2, t1 - t0
        a_times.append(a_time)
        b_times.append(b_time)
        order_flags.append(a_first)

    return analyze(
        a_times,
        b_times,
        seed=seed,
        order_flags=order_flags,
        **analyze_kwargs,
    )


def format_comparison(comp: Comparison) -> str:
    """Human-readable one-block report used by the CLI."""
    lines = [
        "pairedbench  n=%d  method=%s  threshold=%.2fx" % (
            comp.n_pairs,
            comp.method,
            comp.threshold,
        ),
        "  median A          %10.6f ms" % (comp.median_a * 1e3),
        "  median B          %10.6f ms" % (comp.median_b * 1e3),
        "  speedup A/B       %10.4fx  (95%% CI %.4f .. %.4f)"
        % (comp.speedup, comp.ci_low, comp.ci_high),
    ]
    if comp.p_value is not None:
        lines.append("  sign-test p       %10.4f" % comp.p_value)
    lines += [
        "  log-ratio sigma   %10.4f    MDE(80%%)=%.4fx"
        % (comp.sigma_log, math.exp(comp.mde)),
        "  drift rho         %10.3f%s"
        % (comp.drift_rho, "  [FLAGGED]" if comp.drift_flagged else ""),
        "  order effect      %10.4fx" % comp.order_effect,
        "  verdict           %10s" % comp.verdict.upper(),
    ]
    return "\n".join(lines)
