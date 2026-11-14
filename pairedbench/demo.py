"""Two demos: a null control and a genuine implementation difference.

The demo is not an optimization claim; it exists to show that the procedure
says INCONCLUSIVE when there is nothing to find and finds a real gap when
there is one.
"""

from __future__ import annotations

import ast
import csv
import io
import json
import random

from .core import ab_compare, format_comparison

_ROWS = 20_000
_COLS = 6
_PAYLOAD_KEYS = 400


def _csv_text(seed: int = 7) -> str:
    rng = random.Random(seed)
    buf = io.StringIO()
    for i in range(_ROWS):
        buf.write(
            "%d,%s,%.3f,%s,%d,%s\n"
            % (
                i,
                "row%05d" % rng.randrange(100_000),
                rng.random() * 1000.0,
                rng.choice(["alpha", "beta", "gamma", "delta"]),
                rng.randrange(1_000_000),
                "x" * rng.randrange(1, 12),
            )
        )
    return buf.getvalue()


def _json_payload(seed: int = 11) -> str:
    rng = random.Random(seed)
    obj = {
        "k%03d" % i: [rng.randrange(10**6) for _ in range(8)]
        for i in range(_PAYLOAD_KEYS)
    }
    return json.dumps(obj, sort_keys=True)


def run_demo(*, samples: int = 21, warmup: int = 3, seed: int = 20261115) -> dict:
    # 1. Null control: two separately defined but identical closures.
    data = list(range(50_000))

    def null_a():
        return sum(x * x for x in data)

    def null_b():
        return sum(x * x for x in data)

    null = ab_compare(
        null_a, null_b, samples=samples, warmup=warmup, seed=seed
    )

    # 2. Real difference: two stdlib parsers over the same JSON-compatible text.
    payload = _json_payload()
    assert ast.literal_eval(payload) == json.loads(payload)

    def json_arm():
        return json.loads(payload)

    def literal_arm():
        return ast.literal_eval(payload)

    real = ab_compare(
        json_arm, literal_arm, samples=samples, warmup=warmup, seed=seed + 1
    )

    # 3. CSV: C-level reader vs a plain split loop (both genuine implementations).
    text = _csv_text()

    def csv_arm():
        total = 0
        for row in csv.reader(io.StringIO(text)):
            total += len(row)
        return total

    def split_arm():
        total = 0
        for line in text.splitlines():
            total += len(line.split(","))
        return total

    assert csv_arm() == split_arm() == _ROWS * _COLS

    csv_cmp = ab_compare(
        split_arm, csv_arm, samples=samples, warmup=warmup, seed=seed + 2
    )

    return {
        "null_control": null.as_dict(),
        "json_vs_literal_eval": real.as_dict(),
        "split_vs_csv": csv_cmp.as_dict(),
    }


def format_demo(result: dict) -> str:
    blocks = []
    for name, payload in result.items():
        from .core import Comparison

        comp = Comparison(**payload)
        blocks.append("%s\n%s" % (name, format_comparison(comp)))
    return "\n\n".join(blocks)
