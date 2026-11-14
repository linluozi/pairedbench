"""pairedbench: interleaved paired A/B benchmarking with a calibrated verdict."""

__version__ = "0.2.0"

from .core import Comparison, ab_compare, analyze, format_comparison
from .calibrate import run_calibration
from .stats import (
    bootstrap_median_ci,
    holm_adjust,
    holm_reject,
    median,
    minimum_detectable_effect,
    percentile,
    sign_test_p,
    spearman,
)

__all__ = [
    "Comparison",
    "ab_compare",
    "analyze",
    "format_comparison",
    "run_calibration",
    "bootstrap_median_ci",
    "holm_adjust",
    "holm_reject",
    "median",
    "minimum_detectable_effect",
    "percentile",
    "sign_test_p",
    "spearman",
    "__version__",
]
