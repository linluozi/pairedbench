import math
import time
import random

import pytest

from pairedbench.core import ab_compare, analyze, format_comparison


def _ratio_data(ratio, n=15, seed=1):
    rng = random.Random(seed)
    a = [1.0 + rng.random() * 0.1 for _ in range(n)]
    b = [x / ratio for x in a]
    return a, b


def test_two_x_is_detected():
    a, b = _ratio_data(2.0)
    comp = analyze(a, b, seed=3, resamples=500)
    assert comp.verdict == "b_faster"
    assert math.isclose(comp.speedup, 2.0)
    assert comp.ci_low > 1.5
    assert comp.p_value is not None and comp.p_value < 0.01


def test_null_is_inconclusive():
    a = [1.0, 1.1, 0.9, 1.05, 0.95, 1.0, 1.02, 0.98]
    comp = analyze(a, list(a), seed=3, resamples=500)
    assert comp.verdict == "inconclusive"
    assert comp.speedup == 1.0
    assert comp.p_value == 1.0


def test_reverse_direction_is_detected():
    a, b = _ratio_data(0.5)
    comp = analyze(a, b, seed=3, resamples=500)
    assert comp.verdict == "a_faster"
    assert comp.ci_high < 0.75


def test_unpaired_ci_is_wider_under_common_mode_noise():
    rng = random.Random(9)
    a, b = [], []
    for _ in range(21):
        common = math.exp(rng.gauss(0.0, 0.30))
        x = common * math.exp(rng.gauss(0.0, 0.02))
        a.append(x)
        b.append(x * math.exp(rng.gauss(0.0, 0.02)))
    paired = analyze(a, b, seed=5, resamples=400, paired=True)
    unpaired = analyze(a, b, seed=5, resamples=400, paired=False)
    assert (paired.ci_high - paired.ci_low) < (unpaired.ci_high - unpaired.ci_low)
    assert unpaired.p_value is None


def test_drift_is_flagged():
    a = [1.0 + 0.1 * i for i in range(15)]
    b = [x * 0.9 for x in a]
    comp = analyze(a, b, seed=1, resamples=200)
    assert comp.drift_rho > 0.9
    assert comp.drift_flagged is True


def test_order_effect_diagnostic():
    a = [1.0] * 10
    b = [1.0] * 10
    flags = [True] * 5 + [False] * 5
    comp = analyze(a, b, order_flags=flags)
    assert comp.order_effect == 1.0


def test_analysis_is_deterministic():
    a, b = _ratio_data(1.3, n=17, seed=4)
    first = analyze(a, b, seed=11, resamples=300).as_dict()
    second = analyze(a, b, seed=11, resamples=300).as_dict()
    assert first == second


def test_ab_compare_collects_requested_pairs():
    calls = {"a": 0, "b": 0}

    def fn_a():
        calls["a"] += 1

    def fn_b():
        calls["b"] += 1

    comp = ab_compare(fn_a, fn_b, samples=7, warmup=2, seed=1)
    assert comp.n_pairs == 7
    assert calls == {"a": 9, "b": 9}
    assert comp.method == "paired"


def test_bad_inputs_raise():
    with pytest.raises(ValueError):
        analyze([1.0, 2.0], [1.0])
    with pytest.raises(ValueError):
        analyze([1.0, 2.0], [1.0, 2.0])
    with pytest.raises(ValueError):
        analyze([1.0, 2.0, 3.0], [0.0, 1.0, 2.0])
    with pytest.raises(ValueError):
        analyze([1.0, 1.0, 1.0], [1.0, 1.0, 1.0], threshold=1.0)


def test_format_comparison_contains_verdict():
    a, b = _ratio_data(2.0)
    text = format_comparison(analyze(a, b, seed=3, resamples=200))
    assert "VERDICT" not in text
    assert "B_FASTER" in text
    assert "n=15" in text


def test_arm_timings_are_not_swapped_when_b_runs_first():
    # A sleeps ~5 ms and B ~15 ms, so A/B must be ~0.33x.  A swapped-window
    # bug mixes 0.33x and 3.0x pairs into one arm and blows up the interval.
    def fn_a():
        time.sleep(0.005)

    def fn_b():
        time.sleep(0.015)

    comp = ab_compare(fn_a, fn_b, samples=7, warmup=1, seed=20261115)
    assert 0.2 < comp.speedup < 0.5, comp.speedup
    assert comp.ci_high < 0.6, (comp.ci_low, comp.ci_high)
    assert comp.verdict == "a_faster"
