# SEIR Epidemic Simulation Under Different Intervention Policies

**Computational Science course project -- Section 2, Group 1**

Group members: CALIGUID, VENUS KATHLENE B; ARAPON, GERIC M; DUMANDAGAN, ACE F;
RAFOL, SHANE LOWELLE R; DELA CRUZ, CRESADEL M; BARIMBAO, JOASHUA MARL A.

## Problem statement

When an infectious disease emerges in a city, decision makers must choose
between costly interventions: lockdowns, sustained masking, or mass
vaccination -- and often a combination of them. This project builds a complete
computational study of that decision: we implement a five-compartment SEIRV
epidemic model with time-varying transmission and vaccination rates, generate
a documented synthetic COVID-like outbreak dataset for a city of 500,000
people over one year, calibrate the model to the observed reported cases,
and then simulate five intervention policies (baseline, lockdown, masking,
vaccination only, and a combined strategy). The study compares the policies
on peak infectious load, total infections (attack rate), days above a
healthcare capacity threshold, epidemic duration, and the effective
reproduction number, and reports which strategy best protects hospital
capacity.

## Live demo (GitHub Pages)

An interactive browser demo of the model runs at

**https://shuash11.github.io/computational-science-seir/**

Drag the transmission and vaccination controls or click a policy preset; the
SEIRV system is re-integrated instantly in the page. The demo is a JavaScript
port of `seir_model.py` (RK4, 0.02-day step) validated against the Python
pipeline (worst-case peak deviation < 0.05% across the tested parameter
grid); the five presets reproduce the study's scenarios with the calibrated
parameters. Demo sources: `docs/index.html` and `docs/demo_model.js`.

## Model

Five compartments: susceptible `S`, exposed `E`, infectious `I`, recovered
`R`, vaccinated `V`; `N` is the constant population.

```
dS/dt = -beta(t) * S * I / N - nu(t) * S
dE/dt = +beta(t) * S * I / N - sigma * E
dI/dt = +sigma * E - gamma * I
dR/dt = +gamma * I
dV/dt = +nu(t) * S

R_eff(t) = (beta(t) / gamma) * S(t) / N
```

* `beta(t) = beta0 * multiplier(t)` with a piecewise-constant intervention
  schedule (for example `beta x0.45` during a lockdown).
* `nu(t)` is the per-capita vaccination rate (1/day); the number of people
  vaccinated per day is `nu(t) * S(t)`. The documented rollout capacity is a
  nominal 4000 doses/day, implemented as `nu_max = 4000 / N = 0.008 /day`.
* `sigma = 1/3 /day` (mean latent period 3 days) and `gamma = 1/5 /day`
  (mean infectious period 5 days) are fixed literature-based values.
* All numeric parameters live in `config.py` (single source of truth).

The ODE system is integrated with `scipy.integrate.solve_ivp` (RK45,
`rtol=1e-6`, `atol=1e-8`), split into sub-intervals at schedule jump points.

## Requirements

* Python 3.11+ (tested with Python 3.12; `scipy>=1.16` requires 3.11+)
* Packages in `requirements.txt`: numpy, scipy, matplotlib, pandas, and the
  deliverable builders fpdf2, python-pptx, Pillow (plus pypdf for build
  verification).

## Setup

Windows PowerShell:

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Command prompt: use `.venv\Scripts\activate.bat` instead. macOS/Linux:
`source .venv/bin/activate`.

## Run

Everything in one command:

```
python main.py
```

The pipeline generates the dataset if missing, calibrates the model (about a
minute on a typical laptop), simulates the five scenarios, writes
`output/metrics.json`, and renders all figures.

Useful variants:

```
python main.py --regen            # regenerate the synthetic dataset first
python generate_dataset.py        # dataset only (CSV + metadata JSON)
python generate_dataset.py --help # dataset options (e.g. --seed)
```

See `python main.py --help` for pipeline options.

## Generate the report and presentation

After the pipeline has produced the figures and `output/metrics.json`:

```
python make_report.py    # writes output/SEIR_Report.pdf (5-8 pages)
python make_pptx.py      # writes output/SEIR_Presentation.pptx
```

Both builders read `plots/` and `output/metrics.json`, so run `python main.py`
first. `make_report.py` also fails with a non-zero exit when the PDF falls
outside the required 5-8 pages or contains unresolved text placeholders.

## Project structure

```
config.py             All parameters, schedules, paths, and plot style
seir_model.py         SEIRV ODE right-hand side, simulate(), R_eff helper
generate_dataset.py   Creates data/synthetic_epidemic.csv + metadata JSON
calibration.py        Multi-start L-BFGS-B fit of beta0, rho, E0
scenarios.py          Builds/runs the five intervention policies
metrics.py            Scenario and dataset metrics -> output/metrics.json
visualize.py          8 figures -> plots/*.png + plots/all_figures.pdf
main.py               End-to-end pipeline (dataset -> metrics -> figures)
make_report.py        Builds output/SEIR_Report.pdf (fpdf2)
make_pptx.py          Builds output/SEIR_Presentation.pptx (python-pptx)
docs/index.html       Interactive browser demo (served by GitHub Pages)
docs/demo_model.js    JavaScript SEIRV port used by the demo (validated)
requirements.txt      Python dependencies
README.md             This file
data/                 Generated dataset and metadata (created at run time)
plots/                Generated figures and combined PDF
output/               Generated metrics document, PDF report, presentation
```

`make_report.py` and `make_pptx.py` build the final submission deliverables
from the artifacts above; see "Generate the report and presentation".

## Generated artifacts

* `data/synthetic_epidemic.csv` -- 365 daily rows: `date`, `day` (0-based),
  `reported_new_cases`, `cumulative_reported`, `daily_vaccinations`,
  `cumulative_vaccinated`. The dataset is **synthetic** and documented:
  reported cases are `Poisson(rho * daily clinical cases)` with
  `rho = 0.35` ascertainment, drawn with seed 42.
* `data/dataset_metadata.json` -- population, seed, true parameters,
  intervention timeline, generation method, and a summary of the true
  outbreak (honest disclosure that the data is simulated).
* `output/metrics.json` -- `calibration` (fitted `beta0`, `rho`, `E0` plus
  R-squared, RMSE, MAE, multi-start diagnostics), `scenarios` (per-policy
  peak infectious and day, total infections and attack rate, days above
  capacity, epidemic duration, percent reductions vs baseline), `dataset`
  (observed peak/cumulative reported cases) and a UTC `generated_at`
  timestamp. All values are plain JSON numbers.
* `plots/P1_dataset_overview.png` -- reported cases + vaccination rollout
  with intervention timeline markers.
* `plots/P2_calibration_fit.png` -- fitted model vs observed reported cases
  with R-squared, RMSE, MAE annotation.
* `plots/P3_scenarios_infectious.png` -- infectious `I(t)` for the five
  policies with the healthcare capacity line (2000 persons).
* `plots/P4_scenarios_cumulative.png` -- cumulative infections per policy.
* `plots/P5_capacity_days.png` -- capacity overload shading for the baseline
  and the best intervention, with overloaded-day counts.
* `plots/P6_reff.png` -- effective reproduction number `R_eff(t)` per policy
  with the `R_eff = 1` reference line.
* `plots/P7_sensitivity_beta.png` -- uncontrolled-outbreak sweep over
  `R0 = 0.8 ... 4.0`: peak infectious load and attack rate.
* `plots/P8_policy_comparison.png` -- headline metric comparison per policy.
* `plots/all_figures.pdf` -- all eight figures in a single PDF (8 pages).

## Methodology notes

* **Calibration**: `sigma` and `gamma` are fixed at literature values; the
  initial infectious count is fixed at the documented study value; the
  documented intervention timeline is assumed known. `beta0`, `rho` and `E0`
  are fitted with `scipy.optimize.minimize` (L-BFGS-B, bounded, four
  deterministic multi-starts) minimizing the mean squared error on the
  `log1p` scale of reported cases. Fit quality (R-squared, RMSE, MAE) is
  reported in `output/metrics.json`; no numbers are adjusted by hand.
* **Scenarios** are built from the calibrated `beta0`, so all policies share
  the same fitted epidemiology. The `vaccination_only` and `combined`
  policies start vaccination on day 60 (20 days earlier than the observed
  rollout on day 80) as an accelerated-campaign counterfactual.
* **Metrics** (see `metrics.py` for exact definitions): peak infectious and
  its day, total infections = initial exposed + initial infectious +
  cumulative new infections,
  attack rate as percent of population, days with `I > 2000`, epidemic
  duration (first day after which `I` stays below 1), and percent reductions
  versus the baseline scenario.
* **Determinism**: seed 42 is used for the observation noise; calibration and
  all simulations are deterministic.

## Troubleshooting

* **Headless/no-display systems (or matplotlib backend errors)**: the
  pipeline only saves figures and never opens windows, but if the default
  backend causes problems, force the file-only backend:

  ```
  set MPLBACKEND=Agg        (Command Prompt)
  $env:MPLBACKEND="Agg"     (PowerShell)
  ```

* **`data/synthetic_epidemic.csv` missing or stale**: run
  `python main.py --regen` (or `python generate_dataset.py`).
* **Calibration is slow**: it runs four full multi-start fits; expect about a
  minute. The pipeline prints per-start progress so you can see it working.
* **Console shows garbled text**: all pipeline output is ASCII-only; make
  sure the console is not in a legacy code page with a custom font. This does
  not affect generated files.
* **`python` not found**: install Python 3.11+ and make sure it is on
  `PATH`, or use the full path to the interpreter.
