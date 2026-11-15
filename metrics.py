"""Scenario-level and dataset-level metrics for the SEIRV study.

Definitions (evaluated on the daily grid, day index 0..365):

* ``peak_infectious`` / ``peak_day`` -- maximum of ``I(t)`` and the day on
  which it occurs.
* ``total_infections`` -- all infected persons over the horizon: the initial
  exposed and infectious seed counts plus the cumulative new infections
  counted by the model's infection-flow counter ``F(t)``; the attack rate is
  that total as a percentage of the population.
* ``days_above_capacity`` -- number of days (0..364) with
  ``I > config.HEALTHCARE_CAPACITY``.
* ``epidemic_duration_days`` -- first day after which ``I`` stays below 1 for
  the rest of the horizon (``365`` if the epidemic is still active).
* ``reduction_*_percent`` -- reduction of total infections and of the peak
  relative to the baseline scenario.

Also computes the observed dataset metrics and writes the complete
``output/metrics.json`` document consumed by the report and presentation
builders.  Every number is converted to a plain Python ``int``/``float`` so
the JSON is strictly machine-readable.
"""

from __future__ import annotations

import json
from dataclasses import astuple
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import config
from calibration import CalibrationResult
from scenarios import ScenarioOutcome

__all__ = [
    "build_metrics_document",
    "compute_dataset_metrics",
    "compute_scenario_metrics",
    "write_metrics",
]


def _utc_timestamp() -> str:
    """Current UTC time as an ISO-8601 string with a trailing ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _effective_dataset_seed() -> int:
    """The observation-noise seed actually used for the current dataset.

    Read from ``data/dataset_metadata.json`` so that a custom
    ``generate_dataset.py --seed`` run is reported faithfully; falls back to
    ``config.SEED`` when the metadata file is missing or unreadable.
    """
    try:
        with open(config.DATASET_METADATA_JSON, "r", encoding="utf-8") as handle:
            return int(json.load(handle).get("seed", config.SEED))
    except (OSError, ValueError, json.JSONDecodeError):
        return config.SEED


def compute_scenario_metrics(outcome: ScenarioOutcome) -> dict[str, Any]:
    """Compute the metric block for one simulated scenario.

    Args:
        outcome: Scenario name/description plus its simulation result.

    Returns:
        Plain-Python dictionary of metrics (no NumPy types).
    """
    result = outcome.result
    infectious_daily = result.infectious  # one sample per day, day 0..365
    peak_index = int(np.argmax(infectious_daily))
    peak_infectious = float(infectious_daily[peak_index])

    total_infections = float(
        result.initial_state.exposed
        + result.initial_state.infectious
        + result.cumulative_infections[-1]
    )
    attack_rate = 100.0 * total_infections / config.POPULATION

    days_above_capacity = int(
        np.sum(infectious_daily[: config.DAYS] > config.HEALTHCARE_CAPACITY)
    )

    active_indices = np.nonzero(infectious_daily >= 1.0)[0]
    if active_indices.size == 0:
        duration_days = 0
    else:
        duration_days = int(min(active_indices[-1] + 1, config.DAYS))
    still_active = bool(infectious_daily[-1] >= 1.0)

    return {
        "description": outcome.scenario.description,
        "beta_segments": [
            [float(day), float(multiplier)]
            for day, multiplier in outcome.scenario.beta_schedule.segments
        ],
        "vaccination_ramp": (
            [float(value) for value in astuple(outcome.scenario.vaccination_schedule)]
            if outcome.scenario.vaccination_schedule is not None
            else None
        ),
        "peak_infectious": round(peak_infectious, 2),
        "peak_day": peak_index,
        "total_infections": round(total_infections, 2),
        "attack_rate_percent": round(attack_rate, 3),
        "days_above_capacity": days_above_capacity,
        "epidemic_duration_days": duration_days,
        "still_active_at_horizon": still_active,
    }


def compute_dataset_metrics(dataset: pd.DataFrame) -> dict[str, Any]:
    """Compute observed metrics from the synthetic dataset itself."""
    reported = dataset["reported_new_cases"].to_numpy(dtype=float)
    peak_index = int(np.argmax(reported))
    return {
        "observed_peak_reported_cases": int(reported[peak_index]),
        "observed_peak_day": peak_index,
        "cumulative_reported_cases": int(dataset["cumulative_reported"].iloc[-1]),
        "total_vaccinations": int(dataset["daily_vaccinations"].sum()),
        "mean_daily_reported_cases": round(float(reported.mean()), 3),
        "days_with_zero_reported_cases": int(np.sum(reported == 0)),
    }


def _add_baseline_reductions(scenario_metrics: dict[str, dict[str, Any]]) -> None:
    """Add percent reductions versus the baseline scenario, in place."""
    baseline = scenario_metrics["baseline"]
    for name, block in scenario_metrics.items():
        if name == "baseline":
            block["reduction_total_infections_percent"] = None
            block["reduction_peak_infectious_percent"] = None
            continue
        block["reduction_total_infections_percent"] = round(
            100.0 * (1.0 - block["total_infections"] / baseline["total_infections"]), 3
        )
        block["reduction_peak_infectious_percent"] = round(
            100.0 * (1.0 - block["peak_infectious"] / baseline["peak_infectious"]), 3
        )


def build_metrics_document(
    calibration_result: CalibrationResult,
    outcomes: tuple[ScenarioOutcome, ...],
    dataset: pd.DataFrame,
) -> dict[str, Any]:
    """Assemble the full ``metrics.json`` document.

    Args:
        calibration_result: Output of :func:`calibration.calibrate`.
        outcomes: Simulated scenarios from :func:`scenarios.run_scenarios`.
        dataset: The daily dataset dataframe.

    Returns:
        JSON-serializable dictionary with ``calibration``, ``scenarios``,
        ``dataset``, ``study`` and ``generated_at`` blocks.
    """
    diagnostics = dict(calibration_result.diagnostics)
    fitted_parameters = diagnostics.pop("fitted_parameters")

    scenario_metrics = {
        outcome.scenario.name: compute_scenario_metrics(outcome) for outcome in outcomes
    }
    if "baseline" not in scenario_metrics:
        raise ValueError("scenario outcomes must include the baseline scenario")
    _add_baseline_reductions(scenario_metrics)

    return {
        "generated_at": _utc_timestamp(),
        "study": {
            "title": "SEIR epidemic simulation under different intervention policies",
            "course": "Computational Science - Section 2, Group 1",
            "population": config.POPULATION,
            "days": config.DAYS,
            "seed": _effective_dataset_seed(),
            "healthcare_capacity": config.HEALTHCARE_CAPACITY,
            "sigma": config.SIGMA,
            "gamma": config.GAMMA,
            "dataset_file": "data/synthetic_epidemic.csv",
            "data_type": "synthetic (documented generation script)",
        },
        "calibration": {
            "fitted_parameters": fitted_parameters,
            "diagnostics": diagnostics,
        },
        "scenarios": scenario_metrics,
        "dataset": compute_dataset_metrics(dataset),
    }


def write_metrics(
    document: dict[str, Any],
    path: Path = config.METRICS_JSON,
) -> Path:
    """Write the metrics document as indented JSON and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    return path
