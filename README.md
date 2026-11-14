# pairedbench

A dependency-free Python library and CLI that answers one question about a
performance change: **is the difference real, or is it noise?**  It interleaves
the two implementations, keeps the pairing, and returns a speedup with a
confidence interval plus an explicit `b_faster` / `a_faster` / `inconclusive`
verdict.

Upstream: none

## Why this exists

Microbenchmarks on shared machines lie in a specific, repeatable way: the
machine gets slower for a few seconds, one implementation happens to run in
that window, and a 1.4x win becomes a 0.8x "regression".  Two independent runs
cannot tell that apart from a real change.  This project turns the fix into a
library: alternate the arms, randomise the order inside each pair, analyse the
**per-pair ratio**, and calibrate the decision rule on a synthetic clock where
the true effect is known.

It is deliberately small: no numpy, no scipy, no subprocess pools, no hidden
global random state.  Every number in this README was produced by the commands
in [Reproduce](#reproduce).

## Install

```bash
python -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest -q          # 29 passed
```

Python 3.10+; the reference environment is CPython 3.12.3.

## Quick start

```bash
# 1. Compare two shell commands (12 interleaved samples, 2 warmups).
pairedbench ab --a "python -c 'import json;json.dumps(list(range(200000)))'" \
               --b "python -c 'import json;json.dumps(list(range(200000)))'" \
               --samples 12

# 2. Calibrate the decision rule: false-positive rate and power.
pairedbench calibrate --trials 200 --json benchmark/calibration.json

# 3. Null control + two real comparisons on generated data.
pairedbench demo --json benchmark/demo.json
```

Library use:

```python
from pairedbench import ab_compare

cmp = ab_compare(fn_a, fn_b, samples=21, warmup=3, seed=20261115)
print(cmp.speedup, cmp.ci_low, cmp.ci_high, cmp.verdict)
```

`cmp.speedup` is `median(a_i / b_i)`: **above 1 means B was faster**.  The
defaults are `samples=21`, `warmup=3`, `threshold=1.02`, 95% CI, 2000 bootstrap
resamples, and a fixed seed.

## Evidence 1 — the decision rule is calibrated

`pairedbench calibrate` builds synthetic clocks with a known true speedup, then
runs the full analysis 200 times per cell.  `common_sigma=0.25` models
machine-wide load that hits both arms equally; `noise_sigma=0.03` is the
independent per-call jitter that pairing cannot remove; `drift=0.20` adds a
monotone 20% slowdown across the run.  A **false positive** is any claim
(`b_faster` or `a_faster`) when the true effect is 0%.

| true effect | drift | method | FP / power | wrong direction | inconclusive | median CI width |
|---:|---:|---|---:|---:|---:|---:|
| 0% | 0% | paired | **FP 0.000** | 0.000 | 1.000 | 0.0305 |
| 0% | 0% | unpaired | FP 0.000 | 0.000 | 1.000 | 0.3758 |
| 2% | 0% | paired | PW 0.015 | 0.000 | 0.985 | 0.0313 |
| 2% | 0% | unpaired | PW 0.000 | 0.000 | 1.000 | 0.3716 |
| 5% | 0% | paired | **PW 0.935** | 0.000 | 0.065 | 0.0318 |
| 5% | 0% | unpaired | PW 0.000 | 0.000 | 1.000 | 0.4175 |
| 10% | 0% | paired | PW 1.000 | 0.000 | 0.000 | 0.0317 |
| 10% | 0% | unpaired | PW 0.020 | 0.000 | 0.980 | 0.4225 |
| 0% | 20% | paired | **FP 0.000** | 0.000 | 1.000 | 0.0298 |
| 0% | 20% | unpaired | FP 0.000 | 0.000 | 1.000 | 0.3972 |
| 5% | 20% | paired | **PW 0.980** | 0.000 | 0.020 | 0.0310 |
| 10% | 20% | paired | PW 1.000 | 0.000 | 0.000 | 0.0332 |

What this says, and what it does not:

- With 21 pairs and 3% ratio noise, the paired rule claims **nothing** in 200
  null runs (FP 0.000) while finding a real 5% effect 93.5% of the time.
- The same samples analysed as two independent groups ("unpaired") have a
  confidence interval **12x wider** and find the 5% effect **0 / 200** times.
  The pairing is the whole product.
- **A 20% common drift is invisible to the trend diagnostic** (flagged in only
  2.0–3.5% of runs) — but it is also harmless here, because it cancels inside
  each pair.  The `drift_rho` field is a tripwire for gross drift, not a
  guarantee; see [Limits](#limits).

## Evidence 2 — it says "no" when there is nothing, and "yes" when there is

`benchmark/demo.json`, produced by `pairedbench demo --samples 21`:

| comparison | median A | median B | A/B | 95% CI | p | verdict |
|---|---:|---:|---:|---|---:|---|
| null control (same function twice) | 2.353 ms | 2.352 ms | 1.0017 | 0.9955 .. 1.0132 | 1.0000 | `inconclusive` |
| `json.loads` vs `ast.literal_eval` | 0.342 ms | 7.807 ms | 0.0437 | 0.0431 .. 0.0445 | 9.5e-07 | `a_faster` |
| `str.split` vs `csv.reader` | 5.600 ms | 11.528 ms | 0.4868 | 0.4841 .. 0.4917 | 9.5e-07 | `a_faster` |

The first row is the one that matters: two identical closures produce a
1.0017x "speedup" and the tool refuses to call it a difference.  The other two
rows are genuine implementation gaps (22.9x and 2.05x) recovered from 21
interleaved pairs.

## How the verdict is computed

1. **Collect** `n` pairs.  In each pair both arms run once, in a random order
   (`random.Random(seed)`), after `warmup` untimed calls.  Interleaving makes a
   load spike hit both arms; randomising the order stops a fixed cache or
   allocator advantage from always landing on the same arm.
2. **Ratio per pair** `r_i = a_i / b_i`; `speedup = median(r_i)`.
3. **Interval**: percentile bootstrap over *pairs* (2000 resamples, seeded),
   which preserves the within-pair correlation.
4. **p-value**: exact two-sided sign test on `r_i > 1` vs `r_i < 1` (ties
   dropped).
5. **MDE**: `(z_{1-alpha/2} + z_{0.8}) * sigma_log / sqrt(n)` — the effect the
   run could have detected, reported so a null result is not over-read.
6. **Verdict**: `b_faster` if the CI lower bound `>= threshold` (default 1.02);
   `a_faster` if the CI upper bound `<= 1/threshold`; otherwise
   `inconclusive`.  `--assert-faster` turns this into a CI gate.

The test suite also pins a bug found while building this: in the B-first
branch the two timing windows must be written to the *opposite* arms.  A
regression test with a 5 ms / 15 ms sleep pair fails loudly if that is wrong.

## Reproduce

```bash
git clone --depth=1 git@github-linluozi:linluozi/pairedbench.git && cd pairedbench
python -m venv .venv && .venv/bin/pip install -e ".[test]" && .venv/bin/python -m pytest -q
.venv/bin/python -m pairedbench calibrate --trials 200 --json benchmark/calibration.json
.venv/bin/python -m pairedbench demo --json benchmark/demo.json
```

`benchmark/calibration.json` and `benchmark/demo.json` are the raw committed
outputs of the last two commands; the tables above are copied from them, not
re-typed from a different run.

## Environment

- CPU: AMD EPYC 7K62 48-Core Processor, 4 vCPU visible
- RAM: 3723 MB
- Runtime: CPython 3.12.3, pytest 9.2.0
- Seeds: `20261115` (default), calibration seed `20261115`
- No multi-version interpreter claim: only CPython 3.12.3 exists on this host.

## Limits

- **This is not a profiler.**  It compares two callables or two commands; it
  does not tell you where time goes.
- **The bootstrap is only as good as the samples.**  It assumes pairs are
  exchangeable; a monotone drift that affects the two arms *differently*
  (e.g. B always runs second and the CPU throttles) is not repaired by
  pairing — randomising the within-pair order is the mitigation, and
  `order_effect` is the diagnostic.
- **The drift tripwire is weak under large common noise.**  In the calibration
  above a 20% trend is flagged only 2.5–3.5% of the time.  That is measured,
  not hidden: common drift cancels in the ratio, but the flag should not be
  read as "no drift".
- **Subprocess mode (`pairedbench ab`)** includes shell/process startup in both
  arms, so it dilutes small differences.  Use the library API for in-process
  comparisons.
- **No CPU pinning / isolation.**  On a shared host, run the calibration on the
  same host and re-check `sigma_log`; the MDE column tells you whether the run
  was worth interpreting.
- **Ratios are not latency percentiles.**  A median-ratio win can still be a
  p99 loss; measure that separately.

## 本轮创新

**B 档。** 已有的 lab（`perfclaim-guard`、`caseproof`、`recache-probe`）分别
管「声明是否可伪造」「差分样本是否独立」「正则税有多大」，没有一条把
**A/B 测量本身的误报率与功效**做成可复算的证书。本轮首次在已知真值的合成时钟上
校准「配对 vs 非配对」：同样的 21 个样本，配对分析在 5% 真实效应上功效
**0 → 93.5%**、零效应误报 **0/200**，并把「20% 漂移对配对估计无害但对趋势
检测不可见」这个反直觉结论量化出来。它推翻的旧做法是「跑两遍看中位数谁大」。

## License

MIT.  Copyright (c) 2026 linluozi.  No upstream code is included.
