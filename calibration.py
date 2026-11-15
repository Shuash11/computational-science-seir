"""Calibrate the SEIRV model to the synthetic reported-case series.

Fitted parameters
-----------------
* ``beta0`` -- baseline transmission rate (the intervention timeline from the
  documented study design is used during calibration; the fitted value is a
  single multiplier on that timeline).
* ``rho``   -- reporting (ascertainment) fraction.
* ``E0``    -- initial number of exposed individuals.

Fixed parameters (documented, literature-based)
-----------------------------------------------
* ``sigma = 1/3`` (mean latent period 3 days) and ``gamma = 1/5`` (mean
  infectious period 5 days) from :mod:`config`.
* The initial number of infectious individuals equals the documented study
  value (the early trajectory is not sensitive enough to identify E0 and I0
  separately), and the intervention/vaccination timeline is assumed known.

Method
------
The loss is the mean squared error on the ``log1p`` scale between the
modelled expected reported cases (``rho`` times the daily clinical-case flow
``integral of sigma*E``) and the observed reported cases.  The log scale makes
the fit robust across the exponential range of an outbreak.  Minimization uses
``scipy.optimize.minimize`` with the L-BFGS-B algorithm and four deterministic
multi-starts spread across the parameter box (bounds from :mod:`config`).

Diagnostics returned include R-squared, RMSE and MAE on the original reported
scale, log-scale counterparts, the number of starts and how many converged,
and the optimizer status of the best run.  If the best R-squared falls below
``config.CALIBRATION_MIN_R_SQUARED`` the warning value ``meets_target`` is set
to ``False`` and the plain value is reported; nothing is adjusted or hidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize

import config
from seir_model import (
    InitialState,
    PiecewiseBeta,
    SEIRParameters,
    VaccinationRamp,
    simulate,
)

__all__ = [
    "CalibratedParameters",
    "CalibrationResult",
    "calibrate",
    "diagnose_fit",
]

# Integration sample grid for the calibration objective (one sample per day).
_GRID_STEP: float = 1.0

# Penalty returned when the ODE solver fails for an extreme parameter guess.
_SOLVER_PENALTY: float = 1e9


@dataclass(frozen=True)
class CalibratedParameters:
    """Parameters fitted to the observed reported-case series."""

    beta0: float
    rho: float
    e0: float


@dataclass
class CalibrationResult:
    """Fitted parameters, diagnostics and the fitted-vs-observed curves.

    Attributes:
        parameters: The fitted parameter triple.
        diagnostics: Plain-Python dictionary of fit-quality numbers.
        days: Day index (0-based) for the curve arrays.
        observed_reported: Observed reported cases per day.
        fitted_reported: Expected reported cases per day under the fitted
            parameters (``rho`` times the clinical-case flow).
    """

    parameters: CalibratedParameters
    diagnostics: dict[str, Any]
    days: np.ndarray
    observed_reported: np.ndarray
    fitted_reported: np.ndarray


def _simulate_daily_clinical_cases(beta0: float, e0: float) -> np.ndarray:
    """Daily clinical-case flow under the dataset's documented timeline."""
    params = SEIRParameters(
        population=config.POPULATION,
        beta0=beta0,
        sigma=config.SIGMA,
        gamma=config.GAMMA,
    )
    interventions = PiecewiseBeta(beta0, config.DATASET_BETA_SEGMENTS)
    vaccination = VaccinationRamp(*config.DATASET_VACCINATION_RAMP)
    initial_state = InitialState.from_seed_counts(
        population=config.POPULATION,
        exposed=e0,
        infectious=config.TRUE_INITIAL_INFECTIOUS,
    )
    t_eval = np.arange(0.0, config.DAYS + _GRID_STEP / 2.0, _GRID_STEP)
    result = simulate(
        params,
        (0.0, float(config.DAYS)),
        interventions=interventions,
        vaccination=vaccination,
        initial_state=initial_state,
        t_eval=t_eval,
    )
    return result.daily_clinical_cases()


def _loss(
    x: np.ndarray,
    observed_reported: np.ndarray,
) -> float:
    """MSE on the log1p scale between modelled and observed reported cases."""
    beta0, rho, e0 = float(x[0]), float(x[1]), float(x[2])
    try:
        clinical = _simulate_daily_clinical_cases(beta0, e0)
    except (RuntimeError, ValueError):
        return _SOLVER_PENALTY
    model_reported = np.maximum(rho * clinical, 0.0)
    residual = np.log1p(model_reported) - np.log1p(observed_reported)
    return float(np.mean(residual**2))


def diagnose_fit(observed: np.ndarray, fitted: np.ndarray) -> dict[str, float]:
    """Fit-quality numbers comparing observed and fitted reported cases.

    Args:
        observed: Observed reported cases per day.
        fitted: Expected reported cases per day under the fitted parameters.

    Returns:
        Dictionary with R-squared, RMSE and MAE on the reported scale and
        their log1p-scale counterparts.
    """
    observed = np.asarray(observed, dtype=float)
    fitted = np.asarray(fitted, dtype=float)
    residual = observed - fitted
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((observed - observed.mean()) ** 2))
    log_residual = np.log1p(observed) - np.log1p(fitted)
    log_ss_res = float(np.sum(log_residual**2))
    log_ss_tot = float(np.sum((np.log1p(observed) - np.log1p(observed).mean()) ** 2))
    return {
        "r_squared": 1.0 - ss_res / ss_tot,
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "mae": float(np.mean(np.abs(residual))),
        "r_squared_log1p": 1.0 - log_ss_res / log_ss_tot,
        "rmse_log1p": float(np.sqrt(np.mean(log_residual**2))),
    }


def calibrate(
    dataset: pd.DataFrame,
    verbose: bool = True,
) -> CalibrationResult:
    """Fit ``beta0``, ``rho`` and ``E0`` to the reported-case series.

    Args:
        dataset: Daily dataset with a ``reported_new_cases`` column.
        verbose: Print one progress line per multi-start.

    Returns:
        A :class:`CalibrationResult` with parameters, diagnostics and the
        fitted-vs-observed daily curves.
    """
    observed_reported = dataset["reported_new_cases"].to_numpy(dtype=float)
    if observed_reported.size != config.DAYS:
        raise ValueError(
            f"expected {config.DAYS} daily observations, got {observed_reported.size}"
        )

    lower = np.array([config.CALIBRATION_BOUNDS[key][0] for key in ("beta0", "rho", "e0")])
    upper = np.array([config.CALIBRATION_BOUNDS[key][1] for key in ("beta0", "rho", "e0")])
    bounds = list(zip(lower.tolist(), upper.tolist()))

    optimizations = []
    for index, start in enumerate(config.CALIBRATION_STARTS, start=1):
        outcome = minimize(
            _loss,
            x0=np.array(start, dtype=float),
            args=(observed_reported,),
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 300, "ftol": 1e-12, "gtol": 1e-8},
        )
        optimizations.append(outcome)
        if verbose:
            print(
                f"[calibration] start {index}/{len(config.CALIBRATION_STARTS)} "
                f"beta0={start[0]:.2f} rho={start[1]:.2f} E0={start[2]:.0f} "
                f"-> loss={outcome.fun:.6f} success={bool(outcome.success)}"
            )
    best = min(optimizations, key=lambda result: float(result.fun))
    parameters = CalibratedParameters(
        beta0=float(best.x[0]),
        rho=float(best.x[1]),
        e0=float(best.x[2]),
    )

    fitted_reported = parameters.rho * _simulate_daily_clinical_cases(
        parameters.beta0, parameters.e0
    )
    fit_metrics = diagnose_fit(observed_reported, fitted_reported)
    diagnostics: dict[str, Any] = {
        "fitted_parameters": {
            "beta0": parameters.beta0,
            "rho": parameters.rho,
            "e0": parameters.e0,
        },
        **fit_metrics,
        "loss_log1p_mse": float(best.fun),
        "multistart_losses": [float(result.fun) for result in optimizations],
        "n_starts": len(optimizations),
        "n_converged": int(sum(bool(result.success) for result in optimizations)),
        "optimizer_success": bool(best.success),
        "optimizer_message": str(best.message),
        "optimizer_iterations": int(best.nit),
        "target_r_squared": config.CALIBRATION_MIN_R_SQUARED,
        "meets_target": bool(fit_metrics["r_squared"] >= config.CALIBRATION_MIN_R_SQUARED),
        "fixed_parameters": {
            "sigma": config.SIGMA,
            "gamma": config.GAMMA,
            "initial_infectious": config.TRUE_INITIAL_INFECTIOUS,
        },
        "assumptions": (
            "sigma and gamma fixed at literature values; initial infectious "
            "count fixed at the documented study value; the documented "
            "intervention and vaccination timeline is assumed known."
        ),
    }

    if verbose:
        print(
            f"[calibration] best: beta0={parameters.beta0:.4f} "
            f"rho={parameters.rho:.4f} E0={parameters.e0:.1f} "
            f"R2={diagnostics['r_squared']:.4f} "
            f"RMSE={diagnostics['rmse']:.2f} "
            f"(target R2 >= {config.CALIBRATION_MIN_R_SQUARED:.2f}, "
            f"meets_target={diagnostics['meets_target']})"
        )

    return CalibrationResult(
        parameters=parameters,
        diagnostics=diagnostics,
        days=np.arange(config.DAYS, dtype=np.int64),
        observed_reported=observed_reported,
        fitted_reported=fitted_reported,
    )
