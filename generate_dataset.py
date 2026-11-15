"""Generate the synthetic observed epidemic dataset.

The dataset is a simulated COVID-like outbreak in a mid-sized city
(``config.POPULATION``, ``config.DAYS`` days).  It is generated with the
SEIRV model (:mod:`seir_model`) using the documented "true" parameters and
intervention timeline from :mod:`config`, and is fully synthetic -- it is not
real surveillance data.

Observation model (documented in ``data/dataset_metadata.json``):

* Daily new clinical cases are the integral of ``sigma * E(t)`` over each
  calendar day, evaluated exactly at day boundaries from the cumulative
  clinical counter ``C(t) = E0 + F(t) - E(t)``.
* Reported new cases are drawn as ``Poisson(rho * clinical_cases)`` per day,
  where ``rho = config.TRUE_REPORTING_FRACTION`` is the ascertainment
  fraction, and stored as integers.
* Daily vaccinations are the modelled number of people completing vaccination
  each day (``nu(t) * S(t)`` integrated over the day), rounded to integers.

Outputs (written into ``config.DATA_DIR``):

* ``synthetic_epidemic.csv`` -- 365 daily rows plus header.
* ``dataset_metadata.json`` -- true parameters, timeline and method.

Run directly (``python generate_dataset.py``) or through ``python main.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config
from seir_model import (
    InitialState,
    PiecewiseBeta,
    SEIRParameters,
    VaccinationRamp,
    simulate,
)

__all__ = ["generate_dataset", "main"]

# Sub-daily integration grid (0.25 day) used to sample the true trajectory.
_FINE_STEP: float = 0.25


def _utc_timestamp() -> str:
    """Current UTC time as an ISO-8601 string with a trailing ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _true_trajectory(seed: int):
    """Simulate the "true" outbreak that underlies the synthetic dataset."""
    params = SEIRParameters(
        population=config.POPULATION,
        beta0=config.TRUE_BETA0,
        sigma=config.SIGMA,
        gamma=config.GAMMA,
    )
    interventions = PiecewiseBeta(config.TRUE_BETA0, config.DATASET_BETA_SEGMENTS)
    vaccination = VaccinationRamp(*config.DATASET_VACCINATION_RAMP)
    initial_state = InitialState.from_seed_counts(
        population=config.POPULATION,
        exposed=config.TRUE_INITIAL_EXPOSED,
        infectious=config.TRUE_INITIAL_INFECTIOUS,
    )
    t_eval = np.arange(0.0, config.DAYS + _FINE_STEP / 2.0, _FINE_STEP)
    result = simulate(
        params,
        (0.0, float(config.DAYS)),
        interventions=interventions,
        vaccination=vaccination,
        initial_state=initial_state,
        t_eval=t_eval,
    )
    return result


def _metadata(
    result, reported: np.ndarray, daily_vaccinations: np.ndarray, seed: int
) -> dict:
    """Build the machine-readable dataset metadata document.

    ``seed`` is the effective observation-noise seed actually used for this
    generation run (it may differ from ``config.SEED`` when ``--seed`` is
    passed), so the metadata always describes the data it accompanies.
    """
    segments = [
        {"day": day, "multiplier": multiplier}
        for day, multiplier in config.DATASET_BETA_SEGMENTS
    ]
    ramp_start, ramp_end, ramp_rate = config.DATASET_VACCINATION_RAMP
    return {
        "title": "Synthetic COVID-like outbreak in a mid-sized city (SEIRV)",
        "data_type": "synthetic",
        "honesty_note": (
            "This dataset is entirely synthetic and was produced by the SEIRV "
            "model in seir_model.py with the parameters below. It does not "
            "contain real surveillance data."
        ),
        "population": config.POPULATION,
        "seed": seed,
        "days": config.DAYS,
        "start_date": config.START_DATE,
        "true_parameters": {
            "beta0": config.TRUE_BETA0,
            "sigma": config.SIGMA,
            "gamma": config.GAMMA,
            "reporting_fraction": config.TRUE_REPORTING_FRACTION,
            "initial_exposed": config.TRUE_INITIAL_EXPOSED,
            "initial_infectious": config.TRUE_INITIAL_INFECTIOUS,
        },
        "intervention_timeline": {
            "beta_segments": segments,
            "beta_timeline_notes": [
                {"day": day, "note": note} for day, note in config.DATASET_TIMELINE_NOTES
            ],
            "vaccination_ramp": {
                "start_day": ramp_start,
                "full_rate_day": ramp_end,
                "peak_rate_per_capita": ramp_rate,
                "nominal_daily_capacity": config.VACCINATION_DAILY_CAPACITY,
            },
        },
        "generation_method": (
            "True SEIRV trajectory integrated with scipy solve_ivp (RK45, "
            "rtol=1e-6, atol=1e-8) on a 0.25-day grid with breakpoint-split "
            "integration at schedule jumps. Daily clinical cases are the "
            "integral of sigma*E over each day (first differences of the "
            "cumulative clinical counter at day boundaries). Reported cases "
            "are drawn per day as Poisson(rho * clinical_cases); daily "
            "vaccinations are the modelled nu(t)*S(t) flow integrated over "
            "each day and rounded to integers. Cumulative columns are running "
            "sums of the daily columns."
        ),
        "observed_summary": {
            "peak_reported_cases": int(reported.max()),
            "peak_reported_day": int(reported.argmax()),
            "cumulative_reported_cases": int(reported.sum()),
            "total_vaccinations": int(daily_vaccinations.sum()),
            "true_total_infections": float(
                config.TRUE_INITIAL_EXPOSED
                + config.TRUE_INITIAL_INFECTIOUS
                + result.cumulative_infections[-1]
            ),
        },
        "generated_at": _utc_timestamp(),
    }


def generate_dataset(seed: int = config.SEED) -> pd.DataFrame:
    """Generate the synthetic dataset and write CSV + metadata JSON.

    Args:
        seed: Seed for the Poisson observation noise (default from config).

    Returns:
        The generated daily dataframe.
    """
    result = _true_trajectory(seed)

    clinical_cases = result.daily_clinical_cases()
    rng = np.random.default_rng(seed)
    lam = np.maximum(config.TRUE_REPORTING_FRACTION * clinical_cases, 1e-9)
    reported = rng.poisson(lam).astype(np.int64)
    daily_vaccinations = np.rint(result.daily_vaccinations()).astype(np.int64)

    dates = pd.date_range(config.START_DATE, periods=config.DAYS, freq="D")
    dataset = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "day": np.arange(config.DAYS, dtype=np.int64),
            "reported_new_cases": reported,
            "cumulative_reported": np.cumsum(reported, dtype=np.int64),
            "daily_vaccinations": daily_vaccinations,
            "cumulative_vaccinated": np.cumsum(daily_vaccinations, dtype=np.int64),
        }
    )

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(config.DATASET_CSV, index=False)
    with open(config.DATASET_METADATA_JSON, "w", encoding="utf-8") as handle:
        json.dump(_metadata(result, reported, daily_vaccinations, seed), handle, indent=2)
        handle.write("\n")

    print("[dataset] synthetic epidemic generated")
    print(f"[dataset] rows: {len(dataset)}  days: {config.DAYS}  seed: {seed}")
    print(f"[dataset] reported cases: peak {int(reported.max())} on day "
          f"{int(reported.argmax())}, cumulative {int(reported.sum())}")
    print(f"[dataset] vaccinations: total {int(daily_vaccinations.sum())}")
    print(f"[dataset] CSV      -> {config.DATASET_CSV}")
    print(f"[dataset] metadata -> {config.DATASET_METADATA_JSON}")
    return dataset


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point for dataset generation."""
    parser = argparse.ArgumentParser(
        prog="python generate_dataset.py",
        description="Generate the synthetic epidemic dataset (CSV + metadata JSON).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=config.SEED,
        help=f"random seed for the observation noise (default: {config.SEED})",
    )
    args = parser.parse_args(argv)
    generate_dataset(seed=args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
