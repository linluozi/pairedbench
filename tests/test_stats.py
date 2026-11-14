import math

import pytest

from pairedbench import stats


def test_median_odd_and_even():
    assert stats.median([3, 1, 2]) == 2.0
    assert stats.median([4, 1, 3, 2]) == 2.5
    with pytest.raises(ValueError):
        stats.median([])


def test_percentile_endpoints_and_interpolation():
    xs = [1.0, 2.0, 3.0, 4.0]
    assert stats.percentile(xs, 0) == 1.0
    assert stats.percentile(xs, 100) == 4.0
    assert stats.percentile(xs, 50) == 2.5
    assert math.isclose(stats.percentile(xs, 25), 1.75)


def test_bootstrap_ci_is_deterministic_and_brackets_median():
    xs = [1.0, 1.1, 0.9, 1.2, 1.0, 0.95, 1.05]
    first = stats.bootstrap_median_ci(xs, resamples=300, seed=42)
    second = stats.bootstrap_median_ci(xs, resamples=300, seed=42)
    assert first == second
    lo, hi = first
    assert lo <= stats.median(xs) <= hi
    assert lo < hi


def test_sign_test_all_positive_is_significant():
    assert stats.sign_test_p([2.0] * 12) < 0.001


def test_sign_test_all_ties_is_one():
    assert stats.sign_test_p([1.0] * 12) == 1.0


def test_sign_test_balanced_is_not_significant():
    ratios = [1.5, 0.7] * 8
    assert stats.sign_test_p(ratios) > 0.5


def test_spearman_perfect_and_reversed():
    xs = [1, 2, 3, 4, 5]
    assert math.isclose(stats.spearman(xs, xs), 1.0)
    assert math.isclose(stats.spearman(xs, list(reversed(xs))), -1.0)


def test_spearman_with_ties_does_not_explode():
    xs = [1, 1, 2, 2, 3]
    ys = [1, 2, 3, 4, 5]
    value = stats.spearman(xs, ys)
    assert -1.0 <= value <= 1.0


def test_mde_shrinks_with_more_pairs_and_grows_with_noise():
    small = stats.minimum_detectable_effect(0.05, 10)
    large = stats.minimum_detectable_effect(0.05, 100)
    assert large < small
    noisy = stats.minimum_detectable_effect(0.10, 100)
    assert noisy > large


def test_mde_matches_normal_approximation():
    # (1.959964 + 0.841621) * 0.04 / sqrt(21)
    expected = 2.801585 * 0.04 / math.sqrt(21)
    assert math.isclose(
        stats.minimum_detectable_effect(0.04, 21), expected, rel_tol=1e-6
    )


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        stats.bootstrap_median_ci([], resamples=10)
    with pytest.raises(ValueError):
        stats.percentile([1.0], 101)
    with pytest.raises(ValueError):
        stats.spearman([1.0], [1.0, 2.0])
    with pytest.raises(ValueError):
        stats.minimum_detectable_effect(0.1, 10, power=0.7)
