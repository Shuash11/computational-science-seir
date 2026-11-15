"""Five intervention policies simulated on the calibrated SEIRV model.

Each scenario is built from the **calibrated** baseline transmission rate
(``beta0`` from :mod:`calibration`), so all policies share the same fitted
epidemiology and start from identical initial conditions (the fitted initial
exposed count and the documented initial infectious count).  Transmission
policies scale ``beta0`` with a piecewise-constant multiplier schedule;
vaccination policies add a per-capita rate ramp.

The five policies (definitions in :mod:`config`):

* ``baseline``         -- no intervention, constant ``beta0``.
* ``lockdown``         -- ``beta x0.45`` on days 40-99, ``beta0 x0.75`` after.
* ``masking``          -- ``beta x0.70`` from day 30 onward.
* ``vaccination_only`` -- no transmission change; vaccination from day 60,
  ramping toward the nominal 4000 doses/day capacity at full susceptibility
  by day 140 (20 days earlier than the rollout in the observed dataset;
  actual daily doses decline as susceptibles are removed).
* ``combined``         -- masking from day 30, the lockdown schedule, and
  accelerated vaccination together.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import config
from seir_model import (
    InitialState,
    PiecewiseBeta,
    SEIRParameters,
    SimulationResult,
    VaccinationRamp,
    simulate,
)

__all__ = ["Scenario", "ScenarioOutcome", "build_scenarios", "run_scenarios"]


@dataclass(frozen=True)
class Scenario:
    """One fully specified intervention policy.

    Attributes:
        name: Short identifier (matches ``config.SCENARIO_DEFINITIONS``).
        description: Human-readable policy summary.
        beta_schedule: Piecewise transmission schedule ``beta(t)``.
        vaccination_schedule: Vaccination rate ramp, or ``None`` for none.
    """

    name: str
    description: str
    beta_schedule: PiecewiseBeta
    vaccination_schedule: VaccinationRamp | None


@dataclass
class ScenarioOutcome:
    """Simulation result of one scenario."""

    scenario: Scenario
    result: SimulationResult


def build_scenarios(calibrated_beta0: float) -> tuple[Scenario, ...]:
    """Instantiate the five configured policies at the calibrated ``beta0``.

    Args:
        calibrated_beta0: Baseline transmission rate fitted by :mod:`calibration`.

    Returns:
        The scenarios in the order defined by ``config.SCENARIO_DEFINITIONS``.
    """
    scenarios = []
    for definition in config.SCENARIO_DEFINITIONS:
        vaccination_schedule = (
            VaccinationRamp(*definition.vaccination_ramp)
            if definition.vaccination_ramp is not None
            else None
        )
        scenarios.append(
            Scenario(
                name=definition.name,
                description=definition.description,
                beta_schedule=PiecewiseBeta(calibrated_beta0, definition.beta_segments),
                vaccination_schedule=vaccination_schedule,
            )
        )
    return tuple(scenarios)


def run_scenarios(
    scenarios: tuple[Scenario, ...],
    params: SEIRParameters,
    initial_state: InitialState,
    t_span: tuple[float, float] = (0.0, float(config.DAYS)),
) -> tuple[ScenarioOutcome, ...]:
    """Simulate every scenario over the full horizon.

    Args:
        scenarios: Scenarios from :func:`build_scenarios`.
        params: Model parameters; ``params.beta0`` should equal the calibrated
            value the schedules are built from (used only when a scenario has
            no transmission schedule).
        initial_state: Common initial compartment occupancies.
        t_span: Integration window in days.

    Returns:
        Outcomes in the same order as ``scenarios``.
    """
    t_eval = np.arange(t_span[0], t_span[1] + 1.0, 1.0)
    outcomes = []
    for scenario in scenarios:
        result = simulate(
            params,
            t_span,
            interventions=scenario.beta_schedule,
            vaccination=scenario.vaccination_schedule,
            initial_state=initial_state,
            t_eval=t_eval,
        )
        outcomes.append(ScenarioOutcome(scenario=scenario, result=result))
    return tuple(outcomes)
