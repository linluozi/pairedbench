"""Calibration of the decision procedure on synthetic clocks.

The point of this module is falsifiability: we know the true speedup of the
synthetic clock, so we can measure how often ``analyze`` claims a difference
that is not there (false positive) and how often it finds one that is
(power).  A benchmark tool that has never been calibrated is just a random
number generator with a nice table around it.
"""

from __future__ import annotations

import math
import random
from typing import Sequence

from .core import analyze

DEFAULT_EFFECTS = (0.0, 0.02, 0.05, 0.10)
DEFAULT_DRIFTS = (0.0, 0.20)


def simulate_pairs(
    rng: random.Random,
    samples: int,
    true_speedup: float,
    *,
    common_sigma: float = 0.25,
    noise_sigma: float = 0.03,
    drift: float = 0.0,
    base: float = 1e-3,
) -> tuple[list[float], list[float]]:
    """Synthetic paired timings.

    ``common_sigma`` models machine-wide load drifting between pairs (it hits
    both implementations equally, which is exactly what pairing can remove).
    ``noise_sigma`` is the independent per-call jitter that pairing cannot
    remove.  ``drift`` adds a monotone slowdown across the run.
    """
    if true_speedup <= 0.0:
        raise ValueError("true_speedup must be positive")
    if samples < 3:
        raise ValueError("samples must be >= 3")
    a_times: list[float] = []
    b_times: list[float] = []
    for i in range(samples):
        progress = i / (samples - 1)
        common = math.exp(rng.gauss(0.0, common_sigma))
        drift_factor = 1.0 + drift * progress
        a = base * common * drift_factor * math.exp(rng.gauss(0.0, noise_sigma))
        b = a / true_speedup * math.exp(rng.gauss(0.0, noise_sigma))
        a_times.append(a)
        b_times.append(b)
    return a_times, b_times


def _seed_for(seed: int, effect: float, drift: float, paired: bool, trial: int) -> int:
    return (
        seed
        + int(round(effect * 1_000_000)) * 1_000_003
        + int(round(drift * 1_000_000)) * 10_007
        + (0 if paired else 1) * 97
        + trial
    )


def run_calibration(
    *,
    effects: Sequence[float] = DEFAULT_EFFECTS,
    drifts: Sequence[float] = DEFAULT_DRIFTS,
    trials: int = 200,
    samples: int = 21,
    common_sigma: float = 0.25,
    noise_sigma: float = 0.03,
    threshold: float = 1.02,
    resamples: int = 300,
    seed: int = 20261115,
    methods: Sequence[str] = ("paired", "unpaired"),
) -> dict:
    """Measure false-positive rate / power of both analysis modes."""
    if trials < 1:
        raise ValueError("trials must be >= 1")
    rows = []
    for drift in drifts:
        for effect in effects:
            for method in methods:
                claims = {"b_faster": 0, "a_faster": 0, "inconclusive": 0}
                widths: list[float] = []
                drift_flags = 0
                for trial in range(trials):
                    rng = random.Random(
                        _seed_for(seed, effect, drift, method == "paired", trial)
                    )
                    a_times, b_times = simulate_pairs(
                        rng,
                        samples,
                        1.0 + effect,
                        common_sigma=common_sigma,
                        noise_sigma=noise_sigma,
                        drift=drift,
                    )
                    comp = analyze(
                        a_times,
                        b_times,
                        threshold=threshold,
                        resamples=resamples,
                        seed=seed + trial,
                        paired=(method == "paired"),
                        drift_threshold=0.6,
                    )
                    claims[comp.verdict] += 1
                    widths.append(comp.ci_high - comp.ci_low)
                    drift_flags += int(comp.drift_flagged)
                n_claims = claims["b_faster"] + claims["a_faster"]
                row = {
                    "effect": effect,
                    "drift": drift,
                    "method": method,
                    "trials": trials,
                    "samples": samples,
                    "correct_direction_rate": claims["b_faster"] / trials,
                    "wrong_direction_rate": claims["a_faster"] / trials,
                    "any_claim_rate": n_claims / trials,
                    "false_positive_rate": (n_claims / trials) if effect == 0.0 else None,
                    "power": (claims["b_faster"] / trials) if effect > 0.0 else None,
                    "inconclusive_rate": claims["inconclusive"] / trials,
                    "median_ci_width": sorted(widths)[len(widths) // 2],
                    "drift_flag_rate": drift_flags / trials,
                }
                rows.append(row)
    return {
        "generator": {
            "trials": trials,
            "samples": samples,
            "common_sigma": common_sigma,
            "noise_sigma": noise_sigma,
            "threshold": threshold,
            "resamples": resamples,
            "seed": seed,
            "note": (
                "common_sigma is machine-wide drift shared by both arms; "
                "noise_sigma is independent per-call jitter"
            ),
        },
        "rows": rows,
    }


def format_calibration(result: dict) -> str:
    lines = [
        "pairedbench calibration  trials=%d samples=%d threshold=%.2fx"
        % (
            result["generator"]["trials"],
            result["generator"]["samples"],
            result["generator"]["threshold"],
        ),
        "  effect  drift  method    FP/power  wrong  inconcl  CI width",
    ]
    for row in result["rows"]:
        if row["effect"] == 0.0:
            rate = "FP=%.3f  " % (row["false_positive_rate"] or 0.0)
        else:
            rate = "PW=%.3f  " % (row["power"] or 0.0)
        lines.append(
            "  %5.1f%%  %5.1f%%  %-8s  %s  %.3f  %.3f    %.4f"
            % (
                row["effect"] * 100.0,
                row["drift"] * 100.0,
                row["method"],
                rate,
                row["wrong_direction_rate"],
                row["inconclusive_rate"],
                row["median_ci_width"],
            )
        )
    return "\n".join(lines)
