from pairedbench.calibrate import format_calibration, run_calibration


def test_calibration_is_deterministic_and_calibrated():
    kwargs = dict(
        effects=(0.0, 0.2),
        drifts=(0.0,),
        trials=10,
        samples=15,
        resamples=40,
        seed=123,
    )
    first = run_calibration(**kwargs)
    second = run_calibration(**kwargs)
    assert first == second

    by_key = {(r["effect"], r["method"]): r for r in first["rows"]}
    null_paired = by_key[(0.0, "paired")]
    assert null_paired["false_positive_rate"] <= 0.2

    real_paired = by_key[(0.2, "paired")]
    assert real_paired["power"] >= 0.8
    assert real_paired["correct_direction_rate"] >= 0.8


def test_calibration_reports_both_methods():
    result = run_calibration(
        effects=(0.0,),
        drifts=(0.0,),
        trials=4,
        samples=12,
        resamples=30,
    )
    methods = {row["method"] for row in result["rows"]}
    assert methods == {"paired", "unpaired"}
    assert result["generator"]["trials"] == 4


def test_format_calibration_has_rows():
    result = run_calibration(
        effects=(0.0, 0.1),
        drifts=(0.0,),
        trials=3,
        samples=12,
        resamples=20,
    )
    text = format_calibration(result)
    assert "pairedbench calibration" in text
    assert "FP=" in text
    assert "PW=" in text
