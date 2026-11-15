"""End-to-end pipeline for the SEIRV intervention-policy study.

Stages:

1. Generate the synthetic dataset if missing (or with ``--regen``).
2. Calibrate ``beta0``, ``rho`` and ``E0`` on the reported-case series.
3. Simulate the five intervention scenarios at the calibrated ``beta0``.
4. Compute metrics and write ``output/metrics.json``.
5. Render all figures to ``plots/`` (PNGs + combined PDF).

Run with ``python main.py`` and add ``--regen`` to rebuild the dataset from
scratch.  Any stage failure prints a clear error and exits non-zero.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from typing import Any

import pandas as pd

import config
from calibration import calibrate
from generate_dataset import generate_dataset
from metrics import build_metrics_document, write_metrics
from scenarios import build_scenarios, run_scenarios
from seir_model import InitialState, SEIRParameters
from visualize import render_all_figures

__all__ = ["main"]


def _load_or_generate_dataset(regenerate: bool) -> pd.DataFrame:
    """Load the dataset, generating it first when missing or requested."""
    if regenerate or not config.DATASET_CSV.exists():
        return generate_dataset(seed=config.SEED)
    dataset = pd.read_csv(config.DATASET_CSV)
    print(f"[1/5] dataset loaded from {config.DATASET_CSV} ({len(dataset)} rows)")
    return dataset


def _print_summary(document: dict[str, Any]) -> None:
    """Print the ASCII scenario-metrics summary table."""
    scenarios = document["scenarios"]
    header = (
        f"{'scenario':<18}{'peak I':>10}{'peak day':>9}{'attack %':>10}"
        f"{'days>cap':>10}{'duration':>10}{'total red. %':>14}"
    )
    print("-" * len(header))
    print(header)
    print("-" * len(header))
    for name, block in scenarios.items():
        reduction = block["reduction_total_infections_percent"]
        reduction_text = "baseline" if reduction is None else f"{reduction:.1f}"
        print(
            f"{name:<18}{block['peak_infectious']:>10,.0f}{block['peak_day']:>9}"
            f"{block['attack_rate_percent']:>10.2f}{block['days_above_capacity']:>10}"
            f"{block['epidemic_duration_days']:>10}{reduction_text:>14}"
        )
    print("-" * len(header))


def main(argv: list[str] | None = None) -> int:
    """Run the full pipeline and return the process exit code."""
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description=(
            "SEIR epidemic simulation under different intervention policies: "
            "dataset -> calibration -> scenarios -> metrics -> figures."
        ),
    )
    parser.add_argument(
        "--regen",
        action="store_true",
        help="regenerate the synthetic dataset even if it already exists",
    )
    args = parser.parse_args(argv)

    print("=" * 72)
    print("SEIR epidemic simulation under different intervention policies")
    print("Computational Science - Section 2, Group 1")
    print("=" * 72)

    try:
        dataset = _load_or_generate_dataset(args.regen)

        print("[2/5] calibration (multi-start L-BFGS-B; this takes about a minute)")
        calibration_result = calibrate(dataset)
        if not calibration_result.diagnostics["meets_target"]:
            print(
                "[2/5] WARNING: calibration R-squared "
                f"{calibration_result.diagnostics['r_squared']:.4f} is below the "
                f"target {config.CALIBRATION_MIN_R_SQUARED:.2f} (reported as-is)."
            )

        print("[3/5] scenarios")
        parameters = SEIRParameters(
            population=config.POPULATION,
            beta0=calibration_result.parameters.beta0,
            sigma=config.SIGMA,
            gamma=config.GAMMA,
        )
        initial_state = InitialState.from_seed_counts(
            population=config.POPULATION,
            exposed=calibration_result.parameters.e0,
            infectious=config.TRUE_INITIAL_INFECTIOUS,
        )
        scenario_definitions = build_scenarios(calibration_result.parameters.beta0)
        outcomes = run_scenarios(scenario_definitions, parameters, initial_state)
        print(f"[3/5] simulated {len(outcomes)} scenarios over {config.DAYS} days")

        print("[4/5] metrics")
        document = build_metrics_document(calibration_result, outcomes, dataset)
        metrics_path = write_metrics(document)
        print(f"[4/5] metrics -> {metrics_path}")

        print("[5/5] figures")
        render_all_figures(dataset, calibration_result, outcomes, document)

        _print_summary(document)
    except Exception as exc:  # noqa: BLE001 - report any stage failure clearly
        print(f"[ERROR] pipeline failed: {exc}")
        traceback.print_exc()
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
