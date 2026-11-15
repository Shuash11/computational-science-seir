"""SEIRV compartmental epidemic model with time-varying controls.

Model structure
---------------
The population of size ``N`` is partitioned into five compartments:

* ``S`` -- susceptible
* ``E`` -- exposed (infected but not yet infectious)
* ``I`` -- infectious
* ``R`` -- recovered (immune)
* ``V`` -- vaccinated (immune)

with the closed system (no births, no deaths, no waning immunity):

    dS/dt = -beta(t) * S * I / N - nu(t) * S
    dE/dt = +beta(t) * S * I / N - sigma * E
    dI/dt = +sigma * E - gamma * I
    dR/dt = +gamma * I
    dV/dt = +nu(t) * S

where

* ``beta(t)`` is the time-varying transmission rate (1/day).  It is modelled
  as ``beta(t) = beta0 * multiplier(t)`` where ``multiplier(t)`` is a
  piecewise-constant intervention schedule (see :class:`PiecewiseBeta`).
* ``nu(t)`` is the time-varying per-capita vaccination rate (1/day); the
  number of people vaccinated per day is ``nu(t) * S(t)`` (see
  :class:`VaccinationRamp`).
* ``sigma = 1 / mean latent period`` and ``gamma = 1 / mean infectious
  period`` (1/day).

The effective reproduction number is

    R_eff(t) = (beta(t) / gamma) * S(t) / N

Integration
-----------
The system is solved with :func:`scipy.integrate.solve_ivp` using the
explicit Runge-Kutta 5(4) method (``RK45``) with ``rtol=1e-6`` and
``atol=1e-8``.  When a schedule contains jump points (for example a lockdown
that multiplies beta from one day to the next), the integration is split into
sub-intervals at those points so that no solver step straddles a
discontinuity.

An auxiliary cumulative-infection counter ``F(t) = integral of
beta(u)*S*I/N du`` is integrated together with the five compartments.  It
does not feed back into the dynamics; it exists so that daily incidence can
be recovered exactly as first differences of ``F`` at day boundaries.
Cumulative clinical cases (onset of infectiousness) then follow from
``C(t) = E0 + F(t) - E(t)`` because every new infection eventually leaves
``E`` either into ``I`` or, at t=0, started there.

This module is pure computation: no plotting and no file I/O.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.integrate import solve_ivp

__all__ = [
    "InitialState",
    "PiecewiseBeta",
    "SEIRParameters",
    "SimulationResult",
    "VaccinationRamp",
    "effective_reproduction_number",
    "seir_rhs",
    "simulate",
]


# ---------------------------------------------------------------------------
# Parameter and state containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SEIRParameters:
    """Epidemiological parameters of the SEIRV model.

    Attributes:
        population: Total population size ``N`` (persons).
        beta0: Baseline transmission rate (1/day).  Used directly when no
            intervention schedule is supplied; a supplied schedule overrides
            it with ``beta(t) = beta0 * multiplier(t)``.
        sigma: Rate of progression from exposed to infectious (1/day).
        gamma: Recovery rate of infectious individuals (1/day).
    """

    population: float
    beta0: float
    sigma: float
    gamma: float

    def __post_init__(self) -> None:
        if self.population <= 0:
            raise ValueError("population must be positive")
        if self.beta0 < 0 or self.sigma <= 0 or self.gamma <= 0:
            raise ValueError("beta0 must be non-negative; sigma and gamma positive")

    @property
    def basic_reproduction_number(self) -> float:
        """Constant-beta basic reproduction number ``R0 = beta0 / gamma``."""
        return self.beta0 / self.gamma


@dataclass(frozen=True)
class InitialState:
    """Initial compartment occupancies of the SEIRV system.

    ``recovered`` and ``vaccinated`` default to zero; the auxiliary
    cumulative-infection counter always starts at zero.
    """

    susceptible: float
    exposed: float
    infectious: float
    recovered: float = 0.0
    vaccinated: float = 0.0

    def __post_init__(self) -> None:
        values = (self.susceptible, self.exposed, self.infectious, self.recovered, self.vaccinated)
        if any(v < 0 for v in values):
            raise ValueError("compartment occupancies must be non-negative")

    @classmethod
    def from_seed_counts(
        cls,
        population: float,
        exposed: float,
        infectious: float,
        recovered: float = 0.0,
        vaccinated: float = 0.0,
    ) -> "InitialState":
        """Build an initial state with ``susceptible = population - seeds``.

        Raises:
            ValueError: If the seeds do not fit inside the population.
        """
        susceptible = population - exposed - infectious - recovered - vaccinated
        if susceptible < 0:
            raise ValueError("initial infected/recovered/vaccinated exceed the population")
        return cls(
            susceptible=susceptible,
            exposed=exposed,
            infectious=infectious,
            recovered=recovered,
            vaccinated=vaccinated,
        )

    @property
    def as_vector(self) -> np.ndarray:
        """State vector ``[S, E, I, R, V, F]`` for the ODE solver (F starts at 0)."""
        return np.array(
            [
                self.susceptible,
                self.exposed,
                self.infectious,
                self.recovered,
                self.vaccinated,
                0.0,
            ],
            dtype=float,
        )


# ---------------------------------------------------------------------------
# Time-varying schedules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PiecewiseBeta:
    """Piecewise-constant intervention schedule for the transmission rate.

    ``beta(t) = beta0 * multiplier(t)`` where ``multiplier(t)`` is the
    multiplier of the latest segment whose ``start_day`` is at or before
    ``t``.  Segments are ``(start_day, multiplier)`` pairs in ascending order
    of ``start_day``, with the first segment usually starting at day 0.
    """

    beta0: float
    segments: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("at least one segment is required")
        starts = [s for s, _ in self.segments]
        if starts != sorted(starts) or len(set(starts)) != len(starts):
            raise ValueError("segment start days must be strictly ascending")
        if any(m <= 0 for _, m in self.segments):
            raise ValueError("segment multipliers must be positive")

    def __call__(self, t: float | np.ndarray) -> float | np.ndarray:
        """Evaluate ``beta(t)`` for a scalar or an array of times."""
        if isinstance(t, (int, float, np.integer, np.floating)):
            # Fast path used inside the ODE right-hand side.
            multiplier = self.segments[0][1]
            for start_day, segment_multiplier in self.segments:
                if float(t) >= start_day:
                    multiplier = segment_multiplier
                else:
                    break
            return self.beta0 * multiplier
        t_array = np.asarray(t, dtype=float)
        starts = np.array([s for s, _ in self.segments], dtype=float)
        multipliers = np.array([m for _, m in self.segments], dtype=float)
        index = np.searchsorted(starts, t_array, side="right") - 1
        index = np.clip(index, 0, len(self.segments) - 1)
        return self.beta0 * multipliers[index]

    @property
    def breakpoints(self) -> tuple[float, ...]:
        """Days at which the schedule jumps (segment start days after the first)."""
        return tuple(s for s, _ in self.segments[1:])


@dataclass(frozen=True)
class VaccinationRamp:
    """Vaccination schedule ramping linearly to a plateau per-capita rate.

    ``nu(t) = 0`` before ``start_day``; it grows linearly to ``peak_rate``
    (1/day) at ``full_rate_day`` and stays constant afterwards.  With
    ``S`` close to ``N`` the daily number of doses is
    ``nu(t) * N`` -- the nominal daily rollout capacity.
    """

    start_day: float
    full_rate_day: float
    peak_rate: float

    def __post_init__(self) -> None:
        if self.full_rate_day <= self.start_day:
            raise ValueError("full_rate_day must be after start_day")
        if self.peak_rate < 0:
            raise ValueError("peak_rate must be non-negative")

    def __call__(self, t: float | np.ndarray) -> float | np.ndarray:
        """Evaluate ``nu(t)`` for a scalar or an array of times."""
        if isinstance(t, (int, float, np.integer, np.floating)):
            # Fast path used inside the ODE right-hand side.
            value = float(t)
            if value <= self.start_day:
                return 0.0
            if value >= self.full_rate_day:
                return self.peak_rate
            fraction = (value - self.start_day) / (self.full_rate_day - self.start_day)
            return self.peak_rate * fraction
        t_array = np.asarray(t, dtype=float)
        fraction = (t_array - self.start_day) / (self.full_rate_day - self.start_day)
        fraction = np.clip(fraction, 0.0, 1.0)
        return self.peak_rate * fraction

    @property
    def breakpoints(self) -> tuple[float, ...]:
        """Days at which the schedule changes slope (ramp start and end)."""
        return (self.start_day, self.full_rate_day)


# ---------------------------------------------------------------------------
# Right-hand side and integration
# ---------------------------------------------------------------------------


def seir_rhs(
    t: float,
    state: np.ndarray,
    params: SEIRParameters,
    interventions: Callable[[float], float] | None = None,
    vaccination: Callable[[float], float] | None = None,
) -> np.ndarray:
    """Right-hand side of the SEIRV system.

    Args:
        t: Current time (days).
        state: ``[S, E, I, R, V, F]`` where ``F`` accumulates new infections.
        params: Population and rate parameters.
        interventions: Callable returning ``beta(t)`` (1/day); ``None`` means
            constant ``params.beta0``.
        vaccination: Callable returning ``nu(t)`` (1/day); ``None`` means no
            vaccination.

    Returns:
        Derivative vector ``[dS/dt, dE/dt, dI/dt, dR/dt, dV/dt, dF/dt]``.
    """
    s, e, i, _r, _v, _f = state
    n = params.population
    beta = params.beta0 if interventions is None else float(interventions(t))
    nu = 0.0 if vaccination is None else float(vaccination(t))
    force_of_infection = beta * s * i / n
    return np.array(
        [
            -force_of_infection - nu * s,
            force_of_infection - params.sigma * e,
            params.sigma * e - params.gamma * i,
            params.gamma * i,
            nu * s,
            force_of_infection,
        ]
    )


@dataclass(frozen=True)
class SimulationResult:
    """Tidy container with the sampled SEIRV trajectory.

    All arrays share the same length as ``t``.  Compartment arrays hold
    persons; ``cumulative_infections`` (``F``) holds the number of new
    infections that occurred after day 0 (the initial exposed/infectious
    seeds are not included there).

    Attributes:
        t: Sample times (days).
        susceptible: ``S(t)`` samples.
        exposed: ``E(t)`` samples.
        infectious: ``I(t)`` samples.
        recovered: ``R(t)`` samples.
        vaccinated: ``V(t)`` samples.
        cumulative_infections: ``F(t)``, cumulative new infections.
        initial_state: Initial compartment occupancies.
        population: Total population size ``N``.
    """

    t: np.ndarray
    susceptible: np.ndarray
    exposed: np.ndarray
    infectious: np.ndarray
    recovered: np.ndarray
    vaccinated: np.ndarray
    cumulative_infections: np.ndarray
    initial_state: InitialState
    population: float = field(default=float("nan"))

    @property
    def cumulative_clinical_cases(self) -> np.ndarray:
        """``C(t) = E0 + F(t) - E(t)``: cumulative cases leaving the exposed stage."""
        return self.initial_state.exposed + self.cumulative_infections - self.exposed

    def _day_boundary_indices(self) -> np.ndarray:
        """Indices of ``t`` that fall on whole-day boundaries from ``t[0]``."""
        if self.t.size < 2:
            raise ValueError("trajectory needs at least two samples")
        step = float(self.t[1] - self.t[0])
        if step <= 0 or not np.allclose(np.diff(self.t), step, rtol=0.0, atol=1e-9):
            raise ValueError("t_eval must be a uniform grid for daily aggregation")
        stride = int(round(1.0 / step))
        if stride < 1 or not np.isclose(stride * step, 1.0, rtol=0.0, atol=1e-9):
            raise ValueError("t_eval step must divide one day exactly")
        n_days = int(round(self.t[-1] - self.t[0]))
        indices = np.arange(n_days + 1) * stride
        if indices[-1] >= self.t.size:
            raise ValueError("t_eval must include the final day boundary")
        return indices

    def daily_new_infections(self) -> np.ndarray:
        """New infections for each whole day of the horizon (length = horizon days)."""
        boundary = self._day_boundary_indices()
        return np.diff(self.cumulative_infections[boundary])

    def daily_clinical_cases(self) -> np.ndarray:
        """New clinical cases (``integral of sigma*E``) for each whole day."""
        boundary = self._day_boundary_indices()
        return np.diff(self.cumulative_clinical_cases[boundary])

    def daily_vaccinations(self) -> np.ndarray:
        """Number of people who complete the vaccination process each day."""
        boundary = self._day_boundary_indices()
        return np.diff(self.vaccinated[boundary])


def _split_interval(
    t_span: tuple[float, float],
    breakpoints: Sequence[float] | None,
    t_eval: np.ndarray,
) -> list[tuple[float, float, np.ndarray]]:
    """Split ``t_span`` at break points and distribute ``t_eval`` accordingly."""
    t0, t1 = t_span
    points = [t0]
    for value in sorted(set(breakpoints or ())):
        if t0 + 1e-9 < value < t1 - 1e-9:
            points.append(float(value))
    points.append(t1)

    intervals: list[tuple[float, float, np.ndarray]] = []
    for start, end in zip(points[:-1], points[1:]):
        mask = (t_eval >= start - 1e-9) & (t_eval <= end + 1e-9)
        sub = t_eval[mask]
        if sub.size == 0 or sub[0] > start + 1e-9:
            sub = np.concatenate(([start], sub))
        if sub[-1] < end - 1e-9:
            sub = np.concatenate((sub, [end]))
        intervals.append((start, end, sub))
    return intervals


def simulate(
    params: SEIRParameters,
    t_span: tuple[float, float],
    interventions: Callable[[float], float] | None = None,
    vaccination: Callable[[float], float] | None = None,
    initial_state: InitialState | None = None,
    t_eval: Sequence[float] | None = None,
    breakpoints: Sequence[float] | None = None,
    rtol: float = 1e-6,
    atol: float = 1e-8,
    max_step: float | None = None,
) -> SimulationResult:
    """Integrate the SEIRV system and return a tidy sampled trajectory.

    Args:
        params: Population and rate parameters.
        t_span: ``(t0, t1)`` integration window in days.
        interventions: Callable returning ``beta(t)``; ``None`` for constant
            ``params.beta0``.  When a :class:`PiecewiseBeta` is supplied its
            ``breakpoints`` should also be passed (or listed explicitly) for
            exact jump handling.
        vaccination: Callable returning ``nu(t)``; ``None`` for none.
        initial_state: Initial compartment occupancies (required).
        t_eval: Uniform sample times inside ``t_span``; must include both
            endpoints and its step must divide one day exactly when daily
            aggregation is needed.  Defaults to one sample per day.
        breakpoints: Extra times at which the integration is split so that no
            solver step straddles a discontinuity.
        rtol: Relative solver tolerance.
        atol: Absolute solver tolerance.
        max_step: Upper bound on the solver step (days); ``None`` lets the
            solver choose freely (accuracy is still controlled by ``rtol``
            and ``atol``).

    Returns:
        A :class:`SimulationResult` sampled at ``t_eval``.

    Raises:
        ValueError: If ``initial_state`` is missing or ``t_eval`` does not
            span ``t_span``.
        RuntimeError: If the ODE solver fails.
    """
    if initial_state is None:
        raise ValueError("initial_state is required (use InitialState.from_seed_counts)")
    t0, t1 = float(t_span[0]), float(t_span[1])
    if t_eval is None:
        t_eval = np.arange(t0, t1 + 1.0, 1.0)
    t_eval = np.asarray(t_eval, dtype=float)
    if np.isclose(t_eval[0], t0) is False or np.isclose(t_eval[-1], t1) is False:
        raise ValueError("t_eval must start at t_span[0] and end at t_span[1]")

    all_breakpoints = list(breakpoints or ())
    for schedule in (interventions, vaccination):
        if schedule is not None and hasattr(schedule, "breakpoints"):
            all_breakpoints.extend(schedule.breakpoints)

    def rk45_rhs(time: float, state: np.ndarray) -> np.ndarray:
        return seir_rhs(time, state, params, interventions, vaccination)

    chain_state = initial_state.as_vector
    times: list[np.ndarray] = []
    states: list[np.ndarray] = []
    step_options: dict[str, float] = {}
    if max_step is not None:
        step_options["max_step"] = max_step
    for start, end, sub_eval in _split_interval((t0, t1), all_breakpoints, t_eval):
        solution = solve_ivp(
            rk45_rhs,
            (start, end),
            chain_state,
            method="RK45",
            t_eval=sub_eval,
            rtol=rtol,
            atol=atol,
            **step_options,
        )
        if not solution.success:
            raise RuntimeError(f"ODE solver failed on interval [{start}, {end}]: {solution.message}")
        times.append(sub_eval)
        states.append(solution.y)
        chain_state = solution.y[:, -1]

    t_all = np.concatenate(times)
    y_all = np.concatenate(states, axis=1)
    keep = np.concatenate(([True], np.diff(t_all) > 1e-12))
    t_all = t_all[keep]
    y_all = y_all[:, keep]

    return SimulationResult(
        t=t_all,
        susceptible=y_all[0],
        exposed=y_all[1],
        infectious=y_all[2],
        recovered=y_all[3],
        vaccinated=y_all[4],
        cumulative_infections=y_all[5],
        initial_state=initial_state,
        population=params.population,
    )


def effective_reproduction_number(
    beta_values: float | np.ndarray,
    susceptible: float | np.ndarray,
    gamma: float,
    population: float,
) -> float | np.ndarray:
    """Effective reproduction number ``R_eff(t) = (beta(t) / gamma) * S(t) / N``.

    Args:
        beta_values: ``beta(t)`` value(s) (1/day).
        susceptible: ``S(t)`` value(s) (persons).
        gamma: Recovery rate (1/day).
        population: Total population size ``N``.

    Returns:
        ``R_eff`` as a float for scalar inputs, otherwise a NumPy array.
    """
    beta = np.asarray(beta_values, dtype=float)
    s = np.asarray(susceptible, dtype=float)
    result = beta / gamma * s / population
    if np.ndim(beta_values) == 0 and np.ndim(susceptible) == 0:
        return float(result)
    return result
