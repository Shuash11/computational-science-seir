"""Central configuration for the SEIRV intervention-policy study.

This module is the single source of truth for every numeric parameter,
schedule, style constant and file path used by the project.  Other modules
import from here so that no magic numbers are scattered through the codebase.
Every text string is ASCII-only (the deliverables must survive consoles and
PDF core fonts that are not Unicode-safe).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file, so the project runs from any cwd)
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
PLOTS_DIR: Path = BASE_DIR / "plots"
OUTPUT_DIR: Path = BASE_DIR / "output"
DATASET_CSV: Path = DATA_DIR / "synthetic_epidemic.csv"
DATASET_METADATA_JSON: Path = DATA_DIR / "dataset_metadata.json"
METRICS_JSON: Path = OUTPUT_DIR / "metrics.json"
FIGURES_PDF: Path = PLOTS_DIR / "all_figures.pdf"

# ---------------------------------------------------------------------------
# Population, horizon, determinism
# ---------------------------------------------------------------------------
SEED: int = 42
POPULATION: int = 500_000
DAYS: int = 365
START_DATE: str = "2023-01-01"  # calendar date of simulation day 0

# ---------------------------------------------------------------------------
# Epidemiological parameters (literature-based; FIXED during calibration)
# ---------------------------------------------------------------------------
SIGMA: float = 1.0 / 3.0  # 1 / mean latent period (1/day): mean 3 days
GAMMA: float = 1.0 / 5.0  # 1 / mean infectious period (1/day): mean 5 days

# ---------------------------------------------------------------------------
# "True" parameters of the synthetic outbreak (used only to generate data)
# ---------------------------------------------------------------------------
TRUE_BETA0: float = 0.44  # baseline transmission rate (1/day); R0 = 2.2
TRUE_REPORTING_FRACTION: float = 0.35  # rho: fraction of clinical cases reported
TRUE_INITIAL_EXPOSED: float = 60.0
TRUE_INITIAL_INFECTIOUS: float = 25.0

# Intervention timeline used to generate the observed dataset (day offsets)
DATASET_BETA_SEGMENTS: tuple[tuple[int, float], ...] = (
    (0, 1.00),  # days 0-39:   uncontrolled spread
    (40, 0.45),  # days 40-99:  strict intervention
    (100, 0.75),  # days 100+:   partial relaxation
)
DATASET_TIMELINE_NOTES: tuple[tuple[int, str], ...] = (
    (40, "Strict measures begin (beta x0.45)"),
    (80, "Vaccination rollout begins"),
    (100, "Partial relaxation (beta x0.75)"),
)

# ---------------------------------------------------------------------------
# Vaccination rollout
# ---------------------------------------------------------------------------
# The ODE term is dS/dt = -nu(t) * S, so nu(t) is a per-capita rate (1/day).
# The documented rollout target is a nominal capacity of 4000 doses per day at
# the full population; with S close to N the daily number of doses is
# nu(t) * S = nu(t) * N, hence the per-capita plateau below.
VACCINATION_DAILY_CAPACITY: float = 4000.0  # nominal doses/day at full population
VACCINATION_RATE_MAX: float = VACCINATION_DAILY_CAPACITY / POPULATION  # 0.008 /day

DATASET_VACCINATION_RAMP: tuple[int, int, float] = (80, 140, VACCINATION_RATE_MAX)
SCENARIO_VACCINATION_RAMP: tuple[int, int, float] = (60, 140, VACCINATION_RATE_MAX)

# ---------------------------------------------------------------------------
# Healthcare capacity
# ---------------------------------------------------------------------------
HEALTHCARE_CAPACITY: int = 2000  # simultaneous infectious individuals

# ---------------------------------------------------------------------------
# Calibration (fit beta0, rho and E0; sigma and gamma stay fixed)
# ---------------------------------------------------------------------------
CALIBRATION_BOUNDS: dict[str, tuple[float, float]] = {
    "beta0": (0.05, 1.0),
    "rho": (0.05, 0.9),
    "e0": (1.0, 5000.0),
}
# Four deterministic multi-starts spread across the parameter box
# (beta0, rho, E0) -- no randomness beyond the global seed anywhere.
CALIBRATION_STARTS: tuple[tuple[float, float, float], ...] = (
    (0.15, 0.15, 500.0),
    (0.30, 0.55, 2500.0),
    (0.55, 0.30, 100.0),
    (0.85, 0.75, 4000.0),
)
CALIBRATION_MIN_R_SQUARED: float = 0.90  # diagnostic target; not enforced


# ---------------------------------------------------------------------------
# Scenario definitions (five intervention policies)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScenarioDefinition:
    """Declarative description of one intervention policy.

    Attributes:
        name: Short identifier used as dictionary key and file label.
        description: Human-readable policy summary (ASCII only).
        beta_segments: ``(start_day, multiplier)`` pairs for
            ``beta(t) = calibrated_beta0 * multiplier(t)``.
        vaccination_ramp: ``(start_day, full_rate_day, peak_rate)`` for the
            per-capita vaccination rate, or ``None`` for no vaccination.
    """

    name: str
    description: str
    beta_segments: tuple[tuple[int, float], ...]
    vaccination_ramp: tuple[int, int, float] | None = None


SCENARIO_DEFINITIONS: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        name="baseline",
        description=(
            "No intervention: transmission stays constant at the calibrated "
            "baseline rate for the full year."
        ),
        beta_segments=((0, 1.0),),
    ),
    ScenarioDefinition(
        name="lockdown",
        description=(
            "Strict measures on days 40-99 (beta x0.45), then partial "
            "relaxation to beta x0.75 from day 100 onward."
        ),
        beta_segments=((0, 1.0), (40, 0.45), (100, 0.75)),
    ),
    ScenarioDefinition(
        name="masking",
        description="Sustained masking from day 30 onward (beta x0.70 per day).",
        beta_segments=((0, 1.0), (30, 0.70)),
    ),
    ScenarioDefinition(
        name="vaccination_only",
        description=(
            "No transmission change; accelerated vaccination starts on day 60 "
            "and ramps toward the nominal 4000 doses/day capacity at full "
            "susceptibility by day 140 (20 days earlier than the observed "
            "rollout; actual daily doses decline as susceptibles are removed)."
        ),
        beta_segments=((0, 1.0),),
        vaccination_ramp=SCENARIO_VACCINATION_RAMP,
    ),
    ScenarioDefinition(
        name="combined",
        description=(
            "Masking from day 30 (x0.70) combined with the lockdown schedule "
            "(x0.45 on days 40-99, x0.75 after) and accelerated vaccination "
            "from day 60; effective multipliers are 0.315 on days 40-99 and "
            "0.525 afterwards."
        ),
        beta_segments=((0, 1.0), (30, 0.70), (40, 0.315), (100, 0.525)),
        vaccination_ramp=SCENARIO_VACCINATION_RAMP,
    ),
)

# ---------------------------------------------------------------------------
# Sensitivity analysis (beta sweep reported as R0 = beta / gamma)
# ---------------------------------------------------------------------------
SENSITIVITY_R0_MIN: float = 0.8
SENSITIVITY_R0_MAX: float = 4.0
SENSITIVITY_R0_POINTS: int = 33

# ---------------------------------------------------------------------------
# Plot style (colorblind-friendly Okabe-Ito palette)
# ---------------------------------------------------------------------------
PALETTE: tuple[str, ...] = (
    "#0072B2",  # blue
    "#E69F00",  # orange
    "#009E73",  # bluish green
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
    "#56B4E9",  # sky blue
    "#000000",  # black
)
SCENARIO_COLORS: dict[str, str] = {
    "baseline": "#D55E00",
    "lockdown": "#0072B2",
    "masking": "#009E73",
    "vaccination_only": "#CC79A7",
    "combined": "#56B4E9",
}
FIGURE_DPI: int = 150
FIGURE_SIZE: tuple[float, float] = (11.0, 5.5)
FIGURE_SIZE_WIDE: tuple[float, float] = (12.0, 5.0)
GRID_ALPHA: float = 0.3
FIGURE_FILENAMES: tuple[str, ...] = (
    "P1_dataset_overview.png",
    "P2_calibration_fit.png",
    "P3_scenarios_infectious.png",
    "P4_scenarios_cumulative.png",
    "P5_capacity_days.png",
    "P6_reff.png",
    "P7_sensitivity_beta.png",
    "P8_policy_comparison.png",
)
