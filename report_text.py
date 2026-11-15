"""Report and presentation text content for the SEIR course project.

Owned by WP2 (Lead). `make_report.py` and `make_pptx.py` consume this module.
Placeholders written as {name} are filled at build time from output/metrics.json
values computed in make_report.py; the prose deliberately avoids hard-coded
numbers so the report always matches the actual pipeline output.

All text is ASCII-safe (fpdf2 core fonts are Latin-1 only).
"""

REPORT_TITLE = "Simulating an Epidemic: SEIR Modeling of Intervention Policies"
REPORT_SUBTITLE = "A Computational Science Study of a Synthetic COVID-Like Outbreak"
COURSE = "Computational Science - Academic Year 2026-2027"
GROUP = "Group 1, Section 2"
MEMBERS = [
    "CALIGUID, VENUS KATHLENE B",
    "ARAPON, GERIC M",
    "DUMANDAGAN, ACE F",
    "RAFOL, SHANE LOWELLE R",
    "DELA CRUZ, CRESADEL M",
    "BARIMBAO, JOASHUA MARL A",
]

# Each section: heading + list of (kind, payload) blocks.
# kind: "p" paragraph | "fig" (path, caption) | "table" key | "bullets" list | "eq" text lines
SECTIONS = [
    {
        "heading": "1. Real-World Problem and Modeling Assumptions",
        "blocks": [
            ("p",
             "When an infectious disease enters a susceptible population, public health officials face "
             "difficult decisions under uncertainty: when to intervene, how strongly, and what trade-offs "
             "each policy carries. Waiting too long can overwhelm hospitals; intervening too aggressively "
             "has social and economic costs. Mathematical modeling is one of the few tools that lets "
             "decision-makers compare the consequences of such policies before deploying them, and "
             "compartmental models have guided real responses, including during the COVID-19 pandemic "
             "(Anderson et al., 2020)."),
            ("p",
             "This study asks a concrete policy question: for a mid-sized city of {population:,} people "
             "facing a COVID-like respiratory outbreak, how do five intervention strategies - doing "
             "nothing, a temporary lockdown, sustained masking, a vaccination campaign, and a combined "
             "strategy - differ in peak hospital demand, total infections, and days spent above healthcare "
             "capacity? We answer it by simulating the outbreak with a SEIRV compartmental model, "
             "calibrating the model to an observed case series, and comparing policy scenarios under "
             "identical conditions."),
            ("p",
             "Modeling assumptions: (1) the population is well mixed, with uniform contact rates; "
             "(2) individuals move through Susceptible, Exposed (latent, not yet infectious), Infectious, "
             "and Removed (immune) states, with vaccination moving Susceptible individuals directly into "
             "a Vaccinated (immune) compartment; (3) immunity does not wane and there is no reinfection "
             "within the one-year horizon; (4) births and non-disease deaths are negligible; (5) the "
             "reported case count is a fixed fraction of new clinical cases (those past the latent "
             "period; under-ascertainment), "
             "corrupted by counting noise; and (6) interventions act only by reducing the transmission "
             "rate or by vaccinating. These are standard simplifications that trade realism for "
             "interpretable, policy-relevant dynamics (Hethcote, 2000)."),
        ],
    },
    {
        "heading": "2. Mathematical and Computational Formulation",
        "blocks": [
            ("p",
             "The outbreak is described by a system of five coupled ordinary differential equations "
             "(ODEs), one per compartment, where N = S + E + I + R + V is constant:"),
            ("eq",
             ["dS/dt = -beta(t) * S * I / N - nu(t) * S",
              "dE/dt = +beta(t) * S * I / N - sigma * E",
              "dI/dt = +sigma * E - gamma * I",
              "dR/dt = +gamma * I",
              "dV/dt = +nu(t) * S"]),
            ("p",
             "Here beta(t) is the time-varying transmission rate, shaped by intervention policies; "
             "sigma = 1/latent period = 1/3 per day; gamma = 1/infectious period = 1/5 per day (values "
             "consistent with COVID-19 literature estimates); and nu(t) is the per-capita vaccination "
             "rate. The basic reproduction number is R0 = beta/gamma, and the time-dependent effective "
             "reproduction number R_eff(t) = (beta(t)/gamma) * S(t)/N determines whether the outbreak "
             "grows (R_eff > 1) or shrinks (R_eff < 1)."),
            ("p",
             "Numerically, the system is integrated with an adaptive Runge-Kutta method "
             "(scipy.integrate.solve_ivp, RK45, relative tolerance 1e-6), which adjusts step size to keep "
             "local error controlled - appropriate for smooth epidemic curves. Policy scenarios are "
             "encoded as piecewise schedules for beta(t) and nu(t), so all scenarios share identical "
             "parameters and initial conditions except for the interventions themselves, making the "
             "comparison causal in the modeling sense."),
            ("p",
             "Parameters are estimated from data by nonlinear least squares: the reported-case flow "
             "predicted by the model, rho * sigma * E(t), is fitted to the observed daily cases, with "
             "rho the ascertainment fraction. We fit the pre-intervention transmission rate beta0, the "
             "reporting fraction rho, and the initial exposed count E0, keeping sigma and gamma fixed at "
             "their literature values to avoid unidentifiability. The intervention timeline is treated as "
             "known - implementation dates are public record in a real deployment - so beta0 is fitted as "
             "a single scale on that schedule. The bounded L-BFGS-B optimizer is run "
             "from multiple starting points to avoid poor local minima, and the loss is computed on "
             "log1p-transformed cases so that the exponential growth phase and the peak are weighted "
             "comparably. Fit quality is reported as R-squared, RMSE, and MAE."),
        ],
    },
    {
        "heading": "3. Generated Dataset and Data-Generation Method",
        "blocks": [
            ("p",
             "Because the assignment's focus is the computational method, the study uses a documented "
             "synthetic dataset that mimics a realistic surveillance series. A hidden 'true' epidemic is "
             "first simulated with known parameters (beta0 = {beta0_true:.2f}, R0_true = {r0_true:.2f}) "
             "and a built-in policy timeline: uncontrolled spread for 40 days, a strict 60-day intervention "
             "(transmission reduced by 55%), a partial relaxation, and a vaccination rollout starting on "
             "day 80 whose rate ramps to a nominal capacity equivalent to 4,000 doses per day at full "
             "susceptibility by day 140 (actual daily doses decline as susceptibles are removed). The "
             "observed series is then generated as the daily clinical-case flow (the integral of sigma*E "
             "over each day) scaled by the reporting fraction rho = {rho_true:.2f} and corrupted with "
             "Poisson counting noise - the same statistical structure as real notification data."),
            ("table", "dataset_summary"),
            ("p",
             "The result is a {days}-day daily series ({total_reported:,} total reported cases) with a "
             "realistic shape: an initial exponential rise cut by the day-40 intervention, a rebound wave "
             "peaking near day {observed_peak_day}, and a vaccination-era tail in which reporting reaches "
             "zero on {zero_days} days, including the final {trailing_zero_days} consecutive days of the "
             "horizon. "
             "Because the true parameters are known by construction, the calibration step (Section 4.1) "
             "has a verifiable ground truth - a methodological advantage real data cannot offer, and the "
             "reason a synthetic dataset was chosen deliberately rather than for convenience."),
            ("fig", ("P1_dataset_overview.png",
                     "Figure 1. The generated dataset: daily reported cases (left axis) with the "
                     "intervention timeline marked, and cumulative vaccinations (right axis).")),
        ],
    },
    {
        "heading": "4. Results and Interpretation",
        "blocks": [
            ("p", "4.1 Calibration. Fitting the SEIRV model to the synthetic surveillance series recovers "
                  "beta0 = {beta0_fit:.3f} (implied R0 = {r0_fit:.2f}) and a reporting fraction of "
                  "rho = {rho_fit:.2f}, with R-squared = {r_squared:.3f} against observed daily cases "
                  "(RMSE = {rmse:,.0f}, MAE = {mae:,.0f}). The fitted curve tracks both the growth phase "
                  "and the intervention-driven turning points, so the scenario analysis in Section 4.2 is "
                  "anchored to a model consistent with the data rather than to guessed parameters."),
            ("fig", ("P2_calibration_fit.png",
                     "Figure 2. Calibration: model-predicted reported cases (line) versus the observed "
                     "synthetic surveillance data (points), with fit diagnostics annotated.")),
            ("p", "4.2 Scenario comparison. All five policies are simulated for {days} days from the same "
                  "calibrated state. The baseline produces {base_peak:,.0f} simultaneously infectious "
                  "individuals at its peak (day {base_peak_day}) and {base_total_pct:.1f}% of the "
                  "population infected over the year. The comparison below shows how each intervention "
                  "reshapes the epidemic curve: flattening (lower peak), delaying (later peak), and "
                  "shrinking (fewer total infections) are distinct effects, and different policies "
                  "achieve them differently."),
            ("fig", ("P3_scenarios_infectious.png",
                     "Figure 3. Infectious individuals over time under the five policies; the dashed "
                     "line marks the healthcare capacity threshold of {capacity:,}.")),
            ("fig", ("P4_scenarios_cumulative.png",
                     "Figure 4. Cumulative infections per scenario: steep early bends reflect "
                     "transmission cuts, later bends reflect vaccination depleting susceptibles.")),
            ("table", "scenario_metrics"),
            ("p", "4.3 Healthcare capacity. Capacity is defined as {capacity:,} simultaneously infectious "
                  "individuals, a proxy for hospital surge limits. Under the baseline the threshold is "
                  "breached for {base_overload_days} days. Notably, flattening alone does not solve this: "
                  "the lockdown cuts the peak by {lockdown_peak_red:.0f}% yet stretches the epidemic at a "
                  "level still above capacity, raising breach days to {lockdown_overload_days}; sustained "
                  "masking behaves similarly ({masking_overload_days} days). Only interventions strong "
                  "enough to drive R_eff well below 1 shorten the overload - the combined strategy holds "
                  "breach days to {combined_overload_days}. Days above capacity are the metric most "
                  "directly tied to excess mortality, since overloaded hospitals raise case fatality "
                  "independent of the infection itself."),
            ("fig", ("P5_capacity_days.png",
                     "Figure 5. Infectious curve versus healthcare capacity: shaded regions mark days "
                     "spent above the surge threshold.")),
            ("p", "4.4 Transmission dynamics and sensitivity. Interventions reduce R_eff, but whether "
                  "it crosses 1 - the tipping point for decline - depends jointly on the intervention's "
                  "strength and the remaining susceptible fraction. Evaluated at full susceptibility, the "
                  "policy multipliers correspond to nominal R_eff values of {lockdown_reff:.2f} for the "
                  "lockdown, {masking_reff:.2f} for masking, {relaxed_reff:.2f} after the day-100 "
                  "relaxation, and {combined_reff:.2f} then {combined_relax_reff:.2f} for the combined "
                  "strategy. The lockdown initially tips the epidemic into decline but cannot prevent a "
                  "rebound once relaxed; masking crosses 1 only as susceptibles deplete; vaccination-only "
                  "never changes transmission and works purely by shrinking the susceptible pool; and only "
                  "the combined strategy keeps its transmission multipliers near or below the tipping "
                  "point throughout. A sensitivity sweep over R0 = 0.8 to 4.0 shows peak demand rising "
                  "steeply and non-linearly with R0, which is why early, aggressive transmission control "
                  "buys disproportionate headroom."),
            ("figpair", [("P6_reff.png",
                          "Figure 6. Effective reproduction number R_eff(t) per scenario; the "
                          "outbreak shrinks whenever R_eff < 1."),
                         ("P7_sensitivity_beta.png",
                          "Figure 7. Sensitivity of peak demand and total attack rate to the "
                          "basic reproduction number R0.")]),
            ("fig", ("P8_policy_comparison.png",
                     "Figure 8. Policy scorecard: peak demand, total infections (% of population), and "
                     "days above capacity per scenario.")),
        ],
    },
    {
        "heading": "5. Findings and Conclusions",
        "blocks": [
            ("bullets", [
                "Interventions lower R_eff, but crossing 1 is not automatic: masking's 0.70x cut reaches "
                "only a nominal {masking_reff:.2f} at full susceptibility and tips the epidemic only as "
                "susceptibles deplete, and vaccination-only shrinks the susceptible pool without touching "
                "transmission at all.",
                "Early transmission cuts slash the peak: lockdown -{lockdown_peak_red:.0f}% and masking "
                "-{masking_peak_red:.0f}% versus baseline, directly reducing acute hospital demand.",
                "Flattening has a hidden cost at low capacity: by stretching the epidemic, lockdown "
                "({lockdown_overload_days} days) and masking ({masking_overload_days} days) spend more "
                "days above the {capacity:,} threshold than the baseline's {base_overload_days}; only "
                "cutting R_eff deepest (combined) compresses overload to {combined_overload_days} days.",
                "Vaccination timing matters more than intent: a ramp starting on day 60 - after the first "
                "wave's momentum - changes little alone ({vacc_total_red:.1f}% total reduction), but the "
                "same ramp layered onto transmission cuts removes {combined_total_red:.0f}% of all "
                "infections ({combined_total_pct:.1f}% attack rate vs {base_total_pct:.1f}% baseline).",
                "Calibration anchors the analysis: recovering the known parameters from noisy data "
                "(R-squared = {r_squared:.3f}) shows the pipeline can infer transmission parameters from "
                "surveillance-style data.",
            ]),
            ("p",
             "For the policy question posed in Section 1, the computational answer is: layered measures "
             "- a strict early intervention plus a fast vaccination ramp - are the only tested strategy "
             "that comes close to containing the outbreak within healthcare capacity, while no single "
             "measure does. The value of the model is not a "
             "point prediction but the ranked, interpretable comparison of policy options under identical "
             "assumptions."),
        ],
    },
    {
        "heading": "6. Limitations",
        "blocks": [
            ("bullets", [
                "Homogeneous mixing ignores age structure, households, and superspreading; structured "
                "models typically show more severe, faster peaks than well-mixed ones.",
                "Parameters sigma and gamma were fixed at literature values, not estimated; misspecified "
                "generation intervals would shift inferred beta and R0.",
                "The synthetic dataset's noise model (Poisson under-reporting) is simpler than real "
                "surveillance artifacts such as weekly reporting cycles and test-capacity effects.",
                "No reinfection, waning immunity, or behavioral feedback (compliance decays during long "
                "interventions in reality, eroding transmission reductions).",
                "Constant ascertainment rho is an approximation; real reporting fractions varied strongly "
                "over the COVID-19 pandemic.",
            ]),
        ],
    },
    {
        "heading": "7. Extensions and Real-World Impact",
        "blocks": [
            ("p",
             "Natural extensions: age- and location-structured models with contact matrices; stochastic "
             "event-driven simulation to quantify uncertainty bands; optimal-control formulations that "
             "minimize infections subject to economic cost constraints; and economic overlays that price "
             "each policy day. The same pipeline - simulate, calibrate by least squares, compare policies "
             "on capacity metrics - transfers directly to real surveillance data, and is the methodological "
             "core of how mathematical epidemiology informs outbreak response (Kermack and McKendrick, "
             "1927; Anderson et al., 2020). Even the negative results carry value: the sensitivity sweep "
             "shows which parameters decision-makers most need to measure early."),
        ],
    },
    {
        "heading": "8. References",
        "blocks": [
            ("refs", [
                "Anderson, R. M., Heesterbeek, H., Klinkenberg, D., & Hollingsworth, T. D. (2020). How will "
                "country-based mitigation strategies influence the course of the COVID-19 epidemic? The "
                "Lancet, 395(10228), 931-934.",
                "Harris, C. R., et al. (2020). Array programming with NumPy. Nature, 585, 357-362.",
                "Hethcote, H. W. (2000). The mathematics of infectious diseases. SIAM Review, 42(4), "
                "599-653.",
                "Hunter, J. D. (2007). Matplotlib: A 2D graphics environment. Computing in Science & "
                "Engineering, 9(3), 90-95.",
                "Kermack, W. O., & McKendrick, A. G. (1927). A contribution to the mathematical theory of "
                "epidemics. Proceedings of the Royal Society A, 115(772), 700-721.",
                "Virtanen, P., et al. (2020). SciPy 1.0: Fundamental algorithms for scientific computing "
                "in Python. Nature Methods, 17, 261-272.",
            ]),
        ],
    },
]


# ---------------------------------------------------------------- presentation
# Slide list: (layout_kind, title, payload). kind: "title" | "bullets" | "image"
# | "two_col" (bullets + image) | "table" | "closing"
PPTX_SLIDES = [
    ("title", REPORT_TITLE,
     {"subtitle": REPORT_SUBTITLE, "course": COURSE, "group": GROUP, "members": MEMBERS}),
    ("bullets", "The Problem",
     ["A COVID-like outbreak hits a city of {population:,} people.",
      "Officials must choose interventions before seeing outcomes.",
      "Too little, too late: hospitals are overwhelmed.",
      "Too much, too long: severe social and economic cost.",
      "Question: which of five policies best controls peak demand, total infections, and days above hospital capacity?"]),
    ("bullets", "Modeling Assumptions",
     ["Well-mixed population of N = {population:,}.",
      "Compartments: Susceptible -> Exposed -> Infectious -> Removed (+ Vaccinated).",
      "Latent period 3 days (sigma = 1/3), infectious period 5 days (gamma = 1/5).",
      "No waning immunity or reinfection within the 1-year horizon.",
      "Only a fraction rho of clinical cases get reported; counts carry noise.",
      "Interventions reduce transmission beta(t) or vaccinate at rate nu(t)."]),
    ("bullets", "The SEIRV Model",
     ["dS/dt = -beta(t) S I / N - nu(t) S",
      "dE/dt = +beta(t) S I / N - sigma E",
      "dI/dt = +sigma E - gamma I",
      "dR/dt = +gamma I        dV/dt = +nu(t) S",
      "R0 = beta / gamma;  R_eff(t) = (beta(t)/gamma) * S(t)/N",
      "Growth while R_eff > 1; decline while R_eff < 1",
      "Integrated with adaptive Runge-Kutta (SciPy solve_ivp, RK45)."]),
    ("bullets", "Methodology",
     ["Generate: simulate a hidden true epidemic, emit noisy daily surveillance data (CSV).",
      "Calibrate: fit beta0, reporting fraction rho, initial exposed E0 by bounded multi-start "
      "least squares on log-cases.",
      "Simulate: five policy scenarios from the calibrated state.",
      "Compare: peak, total burden, capacity breach days, R_eff.",
      "Communicate: 8 Matplotlib figures, metrics, report, slides."]),
    ("two_col", "The Synthetic Dataset",
     {"image": "P1_dataset_overview.png",
      "bullets": ["{days} days, population {population:,}.",
                  "Hidden truth: beta0 = {beta0_true:.2f} (R0 = {r0_true:.2f}).",
                  "Timeline: strict intervention day 40-99, relaxation after.",
                  "Vaccination from day 80, ramping to a nominal 4,000 doses/day capacity.",
                  "Observed cases = {rho_true:.0%} of clinical cases (past latency) + Poisson noise.",
                  "{total_reported:,} total reported cases."]}),
    ("two_col", "Calibration Recovers the Truth",
     {"image": "P2_calibration_fit.png",
      "bullets": ["Fitted: beta0 = {beta0_fit:.3f} -> R0 = {r0_fit:.2f}.",
                  "Reporting fraction rho = {rho_fit:.2f}.",
                  "R-squared = {r_squared:.3f} on daily cases.",
                  "Bounded multi-start L-BFGS-B on log1p-loss.",
      "Model tracks growth phase and both turning points."]}),
    ("image", "Scenario Comparison: Flatten, Delay, Shrink",
     {"image": "P3_scenarios_infectious.png",
      "caption": "Infectious individuals over time; dashed line = capacity ({capacity:,})."}),
    ("image", "Cumulative Burden by Policy",
     {"image": "P4_scenarios_cumulative.png",
      "caption": "Cumulative infections: total attack rate ranges {attack_rate_span_text}."}),
    ("image", "Healthcare Capacity Is the Bottom Line",
     {"image": "P5_capacity_days.png",
      "caption": "Shaded = days above surge capacity ({capacity:,}). Baseline: {base_overload_days} days; "
                 "lockdown flattens but lengthens: {lockdown_overload_days} days; combined: "
                 "{combined_overload_days} days."}),
    ("image", "Every Policy Works Through R_eff",
     {"image": "P6_reff.png",
      "caption": "R_eff(t) by scenario; the epidemic shrinks when R_eff < 1."}),
    ("image", "Sensitivity: Peaks Grow Non-linearly with R0",
     {"image": "P7_sensitivity_beta.png",
      "caption": "Sweeping R0 = 0.8-4.0: peak demand and total attack rate vs R0."}),
    ("two_col", "Policy Scorecard",
     {"image": "P8_policy_comparison.png",
      "bullets": ["Baseline: {base_total_pct:.1f}% infected, peak {base_peak:,.0f}.",
                  "Lockdown: peak -{lockdown_peak_red:.0f}%, but longest capacity breach "
                  "({lockdown_overload_days} days).",
                  "Masking: modest, sustained suppression ({masking_overload_days} breach days).",
                  "Vaccination alone: late ramp, little effect ({vacc_total_red:.1f}% total cut).",
                  "Combined: smallest peak ({combined_peak:,.0f}) and burden ({combined_total_pct:.1f}%).",
                  "Table on next slide gives exact numbers."]}),
    ("table", "Scenario Metrics",
     {"table": "scenario_metrics_pptx",
      "note": "All scenarios share the calibrated initial state; only policies differ."}),
    ("bullets", "Findings",
     ["Interventions lower R_eff; crossing below 1 depends on the multiplier and susceptible "
      "depletion.",
      "Early transmission cuts slash the peak: lockdown -{lockdown_peak_red:.0f}%, masking "
      "-{masking_peak_red:.0f}% vs baseline.",
      "Flattening has a hidden cost: lockdown stretches days above capacity from {base_overload_days} "
      "to {lockdown_overload_days}; only the combined strategy compresses it ({combined_overload_days} "
      "days).",
      "Vaccination timing matters: late alone changes little ({vacc_total_red:.1f}%); layered on "
      "transmission cuts it removes {combined_total_red:.0f}% of infections.",
      "Calibration recovered known parameters from noisy data (R-squared = {r_squared:.3f})."]),
    ("bullets", "Limitations and Extensions",
     ["Well-mixed assumption ignores age structure and superspreading.",
      "Fixed sigma, gamma; no waning immunity or behavioral fatigue.",
      "Synthetic noise is simpler than real surveillance artifacts.",
      "Extensions: age-structured contacts, stochastic simulation, optimal control, real data.",
      "Impact: the simulate-calibrate-compare pipeline is how models guide real outbreak response."]),
    ("closing", "Thank You",
     {"lines": ["Questions and discussion welcome.",
                "Group 1, Section 2 - Computational Science, AY 2026-2027."]}),
]
