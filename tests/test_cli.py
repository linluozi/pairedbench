import json

from pairedbench.cli import main


def test_cli_calibrate_writes_json(tmp_path):
    out = tmp_path / "calibration.json"
    rc = main(
        [
            "calibrate",
            "--trials",
            "6",
            "--samples",
            "12",
            "--resamples",
            "30",
            "--json",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["generator"]["trials"] == 6
    assert len(payload["rows"]) >= 4


def test_cli_demo_writes_json(tmp_path):
    out = tmp_path / "demo.json"
    rc = main(["demo", "--samples", "9", "--json", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text())
    assert set(payload) == {"null_control", "json_vs_literal_eval", "split_vs_csv"}
    assert payload["null_control"]["n_pairs"] == 9


def test_cli_ab_runs_two_commands():
    rc = main(["ab", "--a", "true", "--b", "true", "--samples", "5", "--warmup", "1"])
    assert rc == 0


def test_cli_assert_faster_exit_code():
    # ``true`` cannot be 2x faster than ``true``; the gate must refuse it.
    rc = main(
        [
            "ab",
            "--a",
            "true",
            "--b",
            "true",
            "--samples",
            "5",
            "--warmup",
            "1",
            "--assert-faster",
        ]
    )
    assert rc == 1
