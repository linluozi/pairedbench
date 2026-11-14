"""Command line interface for pairedbench."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import __version__
from .calibrate import format_calibration, run_calibration
from .core import ab_compare, format_comparison
from .demo import format_demo, run_demo
from .stats import holm_adjust


def _write_json(path: str | None, payload: dict) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")


def _cmd_ab(args: argparse.Namespace) -> int:
    def run(command: str):
        return subprocess.run(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    comp = ab_compare(
        lambda: run(args.a),
        lambda: run(args.b),
        samples=args.samples,
        warmup=args.warmup,
        seed=args.seed,
        threshold=args.threshold,
    )
    print(format_comparison(comp))
    _write_json(args.json, comp.as_dict())
    if args.assert_faster:
        return 0 if comp.verdict == "b_faster" else 1
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    result = run_calibration(
        trials=args.trials, samples=args.samples, resamples=args.resamples
    )
    if args.json:
        _write_json(args.json, result)
    else:
        print(format_calibration(result))
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    result = run_demo(samples=args.samples)
    if args.json:
        _write_json(args.json, result)
    else:
        print(format_demo(result))
    return 0


def _cmd_multi(args: argparse.Namespace) -> int:
    """Adjust p-values from several single-comparison JSON reports."""
    rows = []
    for path in args.reports:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        p_value = payload.get("p_value")
        if p_value is None:
            raise SystemExit("%s: no p_value (was the comparison inconclusive?)" % path)
        label = payload.get("label") or path.rsplit("/", 1)[-1]
        rows.append((label, float(p_value), payload.get("speedup"), payload.get("verdict")))

    adjusted = holm_adjust([p for _, p, _, _ in rows])
    table = []
    for (label, p_value, speedup, verdict), adj in zip(rows, adjusted):
        table.append(
            {
                "label": label,
                "p_value": p_value,
                "p_adjusted": adj,
                "speedup": speedup,
                "verdict": verdict,
                "significant": adj <= args.alpha,
            }
        )

    rejected = sum(1 for row in table if row["significant"])
    print("Holm-Bonferroni over %d comparisons (alpha=%.3f)" % (len(table), args.alpha))
    print("  %-28s %8s %10s %9s  %s" % ("label", "raw p", "adjusted p", "speedup", "reject"))
    for row in table:
        speedup = "-" if row["speedup"] is None else "%.3fx" % row["speedup"]
        print(
            "  %-28s %8.4f %10.4f %9s  %s"
            % (row["label"], row["p_value"], row["p_adjusted"], speedup, "yes" if row["significant"] else "no")
        )
    # Family-wise claim: only these survive the multiplicity correction.
    print("  family-wise rejections: %d/%d" % (rejected, len(table)))
    _write_json(args.json, {"alpha": args.alpha, "comparisons": table})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pairedbench",
        description=(
            "Interleaved paired A/B benchmarking with a calibrated verdict."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    ab = sub.add_parser("ab", help="compare two shell commands")
    ab.add_argument("--a", required=True, help="baseline command")
    ab.add_argument("--b", required=True, help="candidate command")
    ab.add_argument("--samples", type=int, default=21)
    ab.add_argument("--warmup", type=int, default=3)
    ab.add_argument("--threshold", type=float, default=1.02)
    ab.add_argument("--seed", type=int, default=20261115)
    ab.add_argument("--json", help="write the raw comparison to this path")
    ab.add_argument(
        "--assert-faster",
        action="store_true",
        help="exit 0 only when the candidate is faster beyond the threshold",
    )
    ab.set_defaults(func=_cmd_ab)

    cal = sub.add_parser("calibrate", help="measure false-positive rate and power")
    cal.add_argument("--trials", type=int, default=200)
    cal.add_argument("--samples", type=int, default=21)
    cal.add_argument("--resamples", type=int, default=300)
    cal.add_argument("--json", help="write the full calibration table to this path")
    cal.set_defaults(func=_cmd_calibrate)

    demo = sub.add_parser("demo", help="run a null control and two real comparisons")
    demo.add_argument("--samples", type=int, default=21)
    demo.add_argument("--json", help="write raw demo results to this path")
    demo.set_defaults(func=_cmd_demo)

    multi = sub.add_parser(
        "multi", help="Holm-adjust p-values from several `ab --json` reports"
    )
    multi.add_argument("reports", nargs="+", help="JSON files written by `ab --json`")
    multi.add_argument("--alpha", type=float, default=0.05)
    multi.add_argument("--json", help="write the adjusted table to this path")
    multi.set_defaults(func=_cmd_multi)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
