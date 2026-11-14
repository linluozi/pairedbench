# benchmark artifacts

Both files are raw, committed outputs of the commands below on the reference
host (CPython 3.12.3, AMD EPYC 7K62, 4 vCPU, 3723 MB).  The README tables are
copied from these files; they were not re-typed from a different run.

```bash
python -m pairedbench calibrate --trials 200 --json benchmark/calibration.json
python -m pairedbench demo --json benchmark/demo.json
```

- `calibration.json` — 200 synthetic trials per (effect, drift, method) cell.
  `generator` records the simulation parameters; `rows` holds the measured
  false-positive rate (effect = 0), power (effect > 0), wrong-direction rate,
  inconclusive rate, median CI width and drift-flag rate.
- `demo.json` — three raw `Comparison` records (`null_control`,
  `json_vs_literal_eval`, `split_vs_csv`) including medians, CI, p-value,
  sigma, MDE, drift rho and verdict.

The runs are seeded (`seed=20261115`) and deterministic; re-running the same
commands on the same Python should reproduce the same rows.
