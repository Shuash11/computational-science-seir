"""Render every study figure to ``plots/*.png`` and ``plots/all_figures.pdf``.

All figures use the same style: the colorblind-friendly palette, axis labels
with units, titles, a light grid, legends and tight layout.  Text is
ASCII-only.  Figures (see ``config.FIGURE_FILENAMES``):

* P1 dataset overview -- reported cases and cumulative vaccinations.
* P2 calibration fit -- fitted vs observed reported cases with diagnostics.
* P3 scenario infectious curves with the healthcare-capacity threshold.
* P4 cumulative infections per scenario.
* P5 capacity overload detail for baseline vs the best intervention (1x2).
* P6 effective reproduction number R_eff(t) per scenario.
* P7 sensitivity sweep of R0 (peak infectious and attack rate).
* P8 policy comparison bars (peak, attack rate, days above capacity; 1x3
  panels because the three metrics have incompatible units and scales).

Only matplotlib is used for plotting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

import config
from calibration import CalibrationResult
from scenarios import ScenarioOutcome
from seir_model import SEIRParameters, effective_reproduction_number, simulate

__all__ = ["render_all_figures"]

_CAPACITY_COLOR = "#CC0000"


def _apply_style() -> None:
    """Apply the shared matplotlib style for every figure."""
    plt.rcParams.update(
        {
            "savefig.dpi": config.FIGURE_DPI,
            "figure.dpi": 100,
            "savefig.bbox": "tight",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "axes.grid": True,
            "grid.alpha": config.GRID_ALPHA,
            "axes.axisbelow": True,
            "legend.frameon": False,
            "lines.linewidth": 1.8,
        }
    )


def _scenario_color(outcome: ScenarioOutcome) -> str:
    return config.SCENARIO_COLORS[outcome.scenario.name]


def _figure_dataset_overview(dataset: pd.DataFrame) -> plt.Figure:
    """P1: reported cases plus cumulative vaccination rollout."""
    fig, ax = plt.subplots(figsize=config.FIGURE_SIZE)
    ax.bar(
        dataset["day"],
        dataset["reported_new_cases"],
        width=0.9,
        color=config.PALETTE[0],
        alpha=0.85,
        label="Reported new cases (daily)",
    )
    ax.set_xlabel(f"Day (0 = {config.START_DATE})")
    ax.set_ylabel("Reported new cases per day")
    ax.set_title("Synthetic epidemic dataset: reported cases and vaccination rollout")

    ax2 = ax.twinx()
    ax2.plot(
        dataset["day"],
        dataset["cumulative_vaccinated"],
        color=config.PALETTE[3],
        linewidth=2.0,
        label="Cumulative vaccinations",
    )
    ax2.set_ylabel("Cumulative vaccinations (persons)")
    ax2.grid(False)

    y_top = float(ax.get_ylim()[1])
    label_heights = (0.97, 0.72, 0.52)
    for (day, label), height in zip(config.DATASET_TIMELINE_NOTES, label_heights):
        ax.axvline(day, color="#555555", linestyle=":", linewidth=1.0, alpha=0.8)
        ax.annotate(
            label,
            xy=(day + 2, y_top * height),
            rotation=90,
            fontsize=7,
            va="top",
            ha="left",
            color="#333333",
            bbox=dict(boxstyle="square,pad=0.15", facecolor="white", edgecolor="none", alpha=0.75),
        )

    handles_left, labels_left = ax.get_legend_handles_labels()
    handles_right, labels_right = ax2.get_legend_handles_labels()
    ax.legend(
        handles_left + handles_right,
        labels_left + labels_right,
        loc="upper left",
    )
    fig.tight_layout()
    return fig


def _figure_calibration_fit(calibration_result: CalibrationResult) -> plt.Figure:
    """P2: fitted model curve against the observed reported cases."""
    fig, ax = plt.subplots(figsize=config.FIGURE_SIZE)
    ax.plot(
        calibration_result.days,
        calibration_result.observed_reported,
        marker=".",
        linestyle="none",
        color="#555555",
        markersize=3.5,
        alpha=0.65,
        label="Observed reported cases (synthetic)",
    )
    ax.plot(
        calibration_result.days,
        calibration_result.fitted_reported,
        color=config.PALETTE[0],
        linewidth=2.0,
        label="Fitted model (rho x daily clinical cases)",
    )
    ax.set_xlabel("Day")
    ax.set_ylabel("Reported new cases per day")
    ax.set_title("Calibration fit: model vs observed reported cases")

    diagnostics = calibration_result.diagnostics
    fitted = diagnostics["fitted_parameters"]
    annotation = (
        f"R2 = {diagnostics['r_squared']:.4f}\n"
        f"RMSE = {diagnostics['rmse']:.1f} cases/day\n"
        f"MAE = {diagnostics['mae']:.1f} cases/day\n"
        f"beta0 = {fitted['beta0']:.4f} /day\n"
        f"rho = {fitted['rho']:.4f}\n"
        f"E0 = {fitted['e0']:.1f}"
    )
    ax.annotate(
        annotation,
        xy=(0.55, 0.95),
        xycoords="axes fraction",
        va="top",
        ha="left",
        fontsize=9,
        bbox=dict(boxstyle="round", facecolor="white", edgecolor="#888888", alpha=0.9),
    )
    ax.legend(loc="upper right")
    fig.tight_layout()
    return fig


def _figure_scenarios_infectious(outcomes: tuple[ScenarioOutcome, ...]) -> plt.Figure:
    """P3: infectious curves of all scenarios with the capacity line."""
    fig, ax = plt.subplots(figsize=config.FIGURE_SIZE)
    for outcome in outcomes:
        ax.plot(
            outcome.result.t,
            outcome.result.infectious,
            color=_scenario_color(outcome),
            label=outcome.scenario.name,
        )
    ax.axhline(
        config.HEALTHCARE_CAPACITY,
        color=_CAPACITY_COLOR,
        linestyle="--",
        linewidth=1.3,
        label=f"Healthcare capacity ({config.HEALTHCARE_CAPACITY})",
    )
    ax.set_xlabel("Day")
    ax.set_ylabel("Infectious individuals (persons)")
    ax.set_title("Infectious population under the five intervention policies")
    ax.legend(loc="upper right")
    fig.tight_layout()
    return fig


def _figure_scenarios_cumulative(outcomes: tuple[ScenarioOutcome, ...]) -> plt.Figure:
    """P4: cumulative infections per scenario."""
    fig, ax = plt.subplots(figsize=config.FIGURE_SIZE)
    for outcome in outcomes:
        cumulative = (
            outcome.result.initial_state.exposed + outcome.result.cumulative_infections
        )
        ax.plot(
            outcome.result.t,
            cumulative / 1000.0,
            color=_scenario_color(outcome),
            label=outcome.scenario.name,
        )
    ax.set_xlabel("Day")
    ax.set_ylabel("Cumulative infections (thousands of persons)")
    ax.set_title("Cumulative infections over one year")
    ax.legend(loc="upper left")
    fig.tight_layout()
    return fig


def _best_intervention_name(metrics_document: dict[str, Any]) -> str:
    """Name of the non-baseline scenario with the fewest total infections."""
    scenarios = metrics_document["scenarios"]
    candidates = {name: block for name, block in scenarios.items() if name != "baseline"}
    return min(candidates, key=lambda name: candidates[name]["total_infections"])


def _figure_capacity_days(
    outcomes: tuple[ScenarioOutcome, ...],
    metrics_document: dict[str, Any],
) -> plt.Figure:
    """P5: capacity overload detail for baseline and the best intervention."""
    by_name = {outcome.scenario.name: outcome for outcome in outcomes}
    best_name = _best_intervention_name(metrics_document)
    fig, axes = plt.subplots(1, 2, figsize=config.FIGURE_SIZE_WIDE, sharey=False)

    for ax, name in zip(axes, ("baseline", best_name)):
        outcome = by_name[name]
        infectious = outcome.result.infectious
        days_above = metrics_document["scenarios"][name]["days_above_capacity"]
        ax.plot(
            outcome.result.t,
            infectious,
            color=_scenario_color(outcome),
            label="Infectious (I)",
        )
        ax.fill_between(
            outcome.result.t,
            infectious,
            config.HEALTHCARE_CAPACITY,
            where=infectious > config.HEALTHCARE_CAPACITY,
            color=_CAPACITY_COLOR,
            alpha=0.2,
            label=f"Above capacity ({days_above} days)",
        )
        ax.axhline(
            config.HEALTHCARE_CAPACITY,
            color=_CAPACITY_COLOR,
            linestyle="--",
            linewidth=1.2,
            label=f"Capacity = {config.HEALTHCARE_CAPACITY}",
        )
        ax.set_xlabel("Day")
        ax.set_ylabel("Infectious individuals (persons)")
        ax.set_title(f"{name}: {days_above} days above capacity")
        ax.legend(loc="upper right", fontsize=8)

    fig.suptitle("Healthcare capacity overload: baseline vs best intervention")
    fig.tight_layout()
    return fig


def _figure_reff(outcomes: tuple[ScenarioOutcome, ...]) -> plt.Figure:
    """P6: effective reproduction number per scenario."""
    fig, ax = plt.subplots(figsize=config.FIGURE_SIZE)
    for outcome in outcomes:
        beta = outcome.scenario.beta_schedule(outcome.result.t)
        reff = effective_reproduction_number(
            beta,
            outcome.result.susceptible,
            config.GAMMA,
            config.POPULATION,
        )
        ax.plot(
            outcome.result.t,
            reff,
            color=_scenario_color(outcome),
            label=outcome.scenario.name,
        )
    ax.axhline(1.0, color="#000000", linestyle="--", linewidth=1.1, label="R_eff = 1")
    ax.set_xlabel("Day")
    ax.set_ylabel("Effective reproduction number R_eff(t)")
    ax.set_title("Effective reproduction number under the five policies")
    ax.set_ylim(bottom=0.0)
    ax.legend(loc="upper right")
    fig.tight_layout()
    return fig


def _sensitivity_curve(
    outcomes: tuple[ScenarioOutcome, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sweep R0 = beta / gamma and return (R0 values, peak I, attack rate %)."""
    initial_state = outcomes[0].result.initial_state
    r0_values = np.linspace(
        config.SENSITIVITY_R0_MIN,
        config.SENSITIVITY_R0_MAX,
        config.SENSITIVITY_R0_POINTS,
    )
    peaks = np.empty_like(r0_values)
    attack_rates = np.empty_like(r0_values)
    t_eval = np.arange(0.0, float(config.DAYS) + 1.0, 1.0)
    for index, r0 in enumerate(r0_values):
        params = SEIRParameters(
            population=config.POPULATION,
            beta0=float(r0) * config.GAMMA,
            sigma=config.SIGMA,
            gamma=config.GAMMA,
        )
        result = simulate(
            params,
            (0.0, float(config.DAYS)),
            initial_state=initial_state,
            t_eval=t_eval,
        )
        peaks[index] = float(result.infectious.max())
        total = initial_state.exposed + float(result.cumulative_infections[-1])
        attack_rates[index] = 100.0 * total / config.POPULATION
    return r0_values, peaks, attack_rates


def _figure_sensitivity_beta(outcomes: tuple[ScenarioOutcome, ...]) -> plt.Figure:
    """P7: no-intervention sensitivity of peak and attack rate to R0."""
    r0_values, peaks, attack_rates = _sensitivity_curve(outcomes)
    fig, ax = plt.subplots(figsize=config.FIGURE_SIZE)
    ax.plot(r0_values, peaks, color=config.PALETTE[0], marker="o", markersize=3.5, label="Peak infectious")
    ax.set_xlabel("Basic reproduction number R0 = beta / gamma (constant beta)")
    ax.set_ylabel("Peak infectious (persons, log scale)")
    ax.set_yscale("log")

    calibrated_r0 = outcomes[0].scenario.beta_schedule.beta0 / config.GAMMA
    ax.axvline(
        calibrated_r0,
        color="#555555",
        linestyle=":",
        linewidth=1.2,
        label=f"Calibrated R0 = {calibrated_r0:.2f}",
    )

    ax2 = ax.twinx()
    ax2.plot(
        r0_values,
        attack_rates,
        color=config.PALETTE[3],
        marker="s",
        markersize=3.0,
        label="Total infections (%)",
    )
    ax2.set_ylabel("Total infections (% of population)")
    ax2.set_ylim(bottom=0.0)
    ax2.grid(False)

    ax.set_title("Sensitivity of an uncontrolled outbreak to R0 (fixed sigma, gamma)")
    handles_left, labels_left = ax.get_legend_handles_labels()
    handles_right, labels_right = ax2.get_legend_handles_labels()
    ax.legend(handles_left + handles_right, labels_left + labels_right, loc="upper left")
    fig.tight_layout()
    return fig


def _figure_policy_comparison(metrics_document: dict[str, Any]) -> plt.Figure:
    """P8: per-scenario comparison of the three headline metrics."""
    scenarios = metrics_document["scenarios"]
    names = list(scenarios.keys())
    panels = (
        ("peak_infectious", "Peak infectious (persons)", "{:,.0f}"),
        ("attack_rate_percent", "Attack rate (% of population)", "{:.1f}"),
        ("days_above_capacity", f"Days above capacity (of {config.DAYS})", "{:,.0f}"),
    )
    fig, axes = plt.subplots(1, 3, figsize=config.FIGURE_SIZE_WIDE)
    for ax, (key, title, number_format) in zip(axes, panels):
        values = [float(scenarios[name][key]) for name in names]
        positions = np.arange(len(names))
        bars = ax.bar(positions, values, color=[config.SCENARIO_COLORS[name] for name in names])
        ax.set_xticks(positions)
        ax.set_xticklabels(names, rotation=20, ha="right", fontsize=8)
        ax.set_title(title)
        for bar, value in zip(bars, values):
            ax.annotate(
                number_format.format(value),
                xy=(bar.get_x() + bar.get_width() / 2.0, value),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7,
            )
    fig.suptitle("Policy comparison across scenarios")
    fig.tight_layout()
    return fig


def render_all_figures(
    dataset: pd.DataFrame,
    calibration_result: CalibrationResult,
    outcomes: tuple[ScenarioOutcome, ...],
    metrics_document: dict[str, Any],
) -> list[Path]:
    """Render every figure to PNG and add it to the combined PDF.

    Args:
        dataset: Daily dataset dataframe.
        calibration_result: Calibration output for the fit plot.
        outcomes: Simulated scenarios.
        metrics_document: Metrics document (for annotations and comparisons).

    Returns:
        Paths of the written PNG files, in figure order.
    """
    config.PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    _apply_style()

    print("[figures] sensitivity sweep (33 R0 values)...")
    figures = (
        (config.FIGURE_FILENAMES[0], _figure_dataset_overview(dataset)),
        (config.FIGURE_FILENAMES[1], _figure_calibration_fit(calibration_result)),
        (config.FIGURE_FILENAMES[2], _figure_scenarios_infectious(outcomes)),
        (config.FIGURE_FILENAMES[3], _figure_scenarios_cumulative(outcomes)),
        (config.FIGURE_FILENAMES[4], _figure_capacity_days(outcomes, metrics_document)),
        (config.FIGURE_FILENAMES[5], _figure_reff(outcomes)),
        (config.FIGURE_FILENAMES[6], _figure_sensitivity_beta(outcomes)),
        (config.FIGURE_FILENAMES[7], _figure_policy_comparison(metrics_document)),
    )

    written: list[Path] = []
    with PdfPages(
        config.FIGURES_PDF,
        metadata={
            "Title": "SEIRV intervention study - all figures",
            "Author": "Computational Science - Section 2, Group 1",
        },
    ) as pdf:
        for filename, figure in figures:
            path = config.PLOTS_DIR / filename
            figure.savefig(path)
            pdf.savefig(figure)
            plt.close(figure)
            written.append(path)
            print(f"[figures] wrote {path.name}")
    print(f"[figures] combined PDF -> {config.FIGURES_PDF}")
    return written
