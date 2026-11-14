"""Tests for the Holm-Bonferroni family-wise correction."""

import json
import math
import random

import pytest

from pairedbench import stats
from pairedbench.cli import main


def _step_down_rejects(p_values, alpha):
    """Independent transcription of Holm's step-down rule (no adjusted values)."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    rejected = [False] * m
    for rank, idx in enumerate(order):
        if p_values[idx] <= alpha / (m - rank):
            rejected[idx] = True
        else:
            break  # step-down stops at the first non-rejection
    return rejected


def test_known_example():
    # Holm's textbook example: m=4, p = .005, .01, .03, .04
    assert stats.holm_adjust([0.01, 0.04, 0.03, 0.005]) == pytest.approx(
        [0.03, 0.06, 0.06, 0.02]
    )


def test_single_and_empty():
    assert stats.holm_adjust([]) == []
    assert stats.holm_adjust([0.02]) == pytest.approx([0.02])
    assert stats.holm_adjust([1.0]) == [1.0]


def test_adjusted_values_bounds_and_monotonicity():
    p_values = [0.9, 0.001, 0.04, 0.04, 0.5]
    adjusted = stats.holm_adjust(p_values)
    assert all(0.0 <= a <= 1.0 for a in adjusted)
    # Larger raw p can never get a smaller adjusted p.
    pairs = sorted(zip(p_values, adjusted))
    for (_, a), (_, b) in zip(pairs, pairs[1:]):
        assert a <= b


def test_rejection_agrees_with_independent_step_down():
    rng = random.Random(20261115)
    cases = 0
    for _ in range(300):
        m = rng.randint(1, 8)
        p_values = [rng.random() for _ in range(m)]
        if rng.random() < 0.3:  # force ties
            p_values = [round(p, 1) for p in p_values]
        for alpha in (0.01, 0.05, 0.1):
            assert stats.holm_reject(p_values, alpha) == _step_down_rejects(
                p_values, alpha
            ), (p_values, alpha)
            cases += 1
    assert cases == 900


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        stats.holm_adjust([-0.1])
    with pytest.raises(ValueError):
        stats.holm_adjust([1.5])
    with pytest.raises(ValueError):
        stats.holm_adjust([math.nan])
    with pytest.raises(ValueError):
        stats.holm_reject([0.5], alpha=0.0)


def test_cli_multi_reads_ab_reports(tmp_path, capsys):
    reports = []
    for i, p in enumerate([0.004, 0.03, 0.2]):
        path = tmp_path / ("cmp%d.json" % i)
        path.write_text(
            json.dumps({"p_value": p, "speedup": 1.2, "verdict": "b_faster"}),
            encoding="utf-8",
        )
        reports.append(str(path))
    out = tmp_path / "adjusted.json"
    rc = main(["multi", *reports, "--json", str(out)])
    assert rc == 0
    text = capsys.readouterr().out
    assert "Holm-Bonferroni over 3 comparisons" in text
    assert "family-wise rejections: 1/3" in text
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [row["significant"] for row in payload["comparisons"]] == [True, False, False]
    # 0.03 is significant alone but not after the 3-way correction.
    assert payload["comparisons"][1]["p_adjusted"] == pytest.approx(0.06)
