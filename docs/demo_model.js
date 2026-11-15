/**
 * demo_model.js - Browser port of the project's SEIRV epidemic model.
 *
 * This is the exact ODE system from seir_model.py, integrated in the browser
 * with a fixed-step classical Runge-Kutta (RK4) scheme so that the class demo
 * can run instantly with zero dependencies. Numerical parity with the Python
 * pipeline (scipy solve_ivp, RK45, rtol=1e-6) is validated by an automated
 * harness; see the repository README and CI.
 *
 * Equations (N = S + E + I + R + V constant):
 *   dS/dt = -beta(t) * S * I / N - nu(t) * S
 *   dE/dt = +beta(t) * S * I / N - sigma * E
 *   dI/dt = +sigma * E - gamma * I
 *   dR/dt = +gamma * I
 *   dV/dt = +nu(t) * S
 *
 * Observation model of the project: reported cases = rho * integral(sigma*E),
 * with rho the ascertainment fraction (not used by the demo charts directly,
 * which show the true latent compartments like the project's figures).
 */

export const DEFAULTS = Object.freeze({
  population: 500000,
  days: 365,
  dt: 0.02,
  sigma: 1 / 3,
  gamma: 1 / 5,
  beta0Fitted: 0.4409, // calibrated in the Python pipeline
  initialExposed: 59.44,
  initialInfectious: 25.0,
  capacity: 2000,
  healthcare: 2000,
});

/** The five project scenarios, reproduced from the pipeline configuration. */
export const PRESETS = Object.freeze({
  baseline: {
    label: "Baseline",
    description: "No intervention: transmission stays at the calibrated rate.",
    reduction: 0, maskStart: 30,
    lockdownReduction: 0, lockdownStart: 40, releaseDay: 100, postReduction: 0,
    vaccStart: 60, vaccRatePerDay: 0,
  },
  lockdown: {
    label: "Lockdown",
    description: "Strict measures days 40-99 (beta x0.45), partial relaxation after.",
    reduction: 0, maskStart: 30,
    lockdownReduction: 55, lockdownStart: 40, releaseDay: 100, postReduction: 25,
    vaccStart: 60, vaccRatePerDay: 0,
  },
  masking: {
    label: "Masking",
    description: "Sustained masking from day 30 (beta x0.70).",
    reduction: 30, maskStart: 30,
    lockdownReduction: 0, lockdownStart: 40, releaseDay: 100, postReduction: 0,
    vaccStart: 60, vaccRatePerDay: 0,
  },
  vaccination_only: {
    label: "Vaccination only",
    description: "No transmission change; vaccination from day 60 ramping to a nominal 4,000 doses/day capacity by day 140 (actual doses decline as susceptibles are removed).",
    reduction: 0, maskStart: 30,
    lockdownReduction: 0, lockdownStart: 40, releaseDay: 100, postReduction: 0,
    vaccStart: 60, vaccRatePerDay: 4000,
  },
  combined: {
    label: "Combined",
    description: "Masking + lockdown schedule + accelerated vaccination (the project's strongest policy).",
    reduction: 30, maskStart: 30,
    lockdownReduction: 55, lockdownStart: 40, releaseDay: 100, postReduction: 25,
    vaccStart: 60, vaccRatePerDay: 4000,
  },
});

/** Build the piecewise beta multiplier schedule from a settings object.
 *  A day-keyed map keeps start days unique and strictly ascending even when
 *  interventions begin on the same day (the stronger, inclusive multiplier
 *  wins because it is written last). */
export function betaSegmentsFrom(settings) {
  const maskMult = 1 - settings.reduction / 100;
  const lockMult = maskMult * (1 - settings.lockdownReduction / 100);
  const postMult = maskMult * (1 - settings.postReduction / 100);
  const release = Math.max(settings.releaseDay, settings.lockdownStart + 5);
  const byDay = new Map([[0, 1]]);
  if (settings.reduction > 0) byDay.set(settings.maskStart, maskMult);
  if (settings.lockdownReduction > 0) byDay.set(settings.lockdownStart, lockMult);
  if (settings.postReduction > 0 || settings.lockdownReduction > 0) {
    byDay.set(release, postMult);
  }
  return [...byDay.entries()].sort((a, b) => a[0] - b[0]);
}

function multiplierAt(segments, t) {
  let mult = 1;
  for (const [day, value] of segments) {
    if (t >= day) mult = value;
    else break;
  }
  return mult;
}

function vaccinationRateAt(vacc, t) {
  if (!vacc || vacc.rateMax <= 0) return 0;
  if (t < vacc.startDay) return 0;
  if (t >= vacc.fullDay) return vacc.rateMax;
  return (vacc.rateMax * (t - vacc.startDay)) / (vacc.fullDay - vacc.startDay);
}

/**
 * Simulate the SEIRV system.
 *
 * @param {object} settings - Slider/preset settings: reduction, maskStart,
 *   lockdownReduction, lockdownStart, releaseDay, postReduction, vaccStart,
 *   vaccRatePerDay, plus optional overrides (r0, capacity, population, days).
 * @returns {object} Daily-sampled trajectories and headline metrics.
 */
export function simulate(settings, options = {}) {
  const N = options.population ?? DEFAULTS.population;
  const days = options.days ?? DEFAULTS.days;
  const dt = options.dt ?? DEFAULTS.dt;
  const sigma = DEFAULTS.sigma;
  const gamma = DEFAULTS.gamma;
  const capacity = options.capacity ?? settings.capacity ?? DEFAULTS.capacity;
  const r0 = settings.r0 ?? (settings.beta0 !== undefined ? settings.beta0 / gamma : 2.2045);
  const beta0 = r0 * gamma;

  const segments = betaSegmentsFrom(settings);
  const rateMax = (settings.vaccRatePerDay ?? 0) / N;
  const vacc = rateMax > 0
    ? { startDay: settings.vaccStart ?? 60, fullDay: (settings.vaccStart ?? 60) + 80, rateMax }
    : null;

  // State: [S, E, I, R, V, F] where F is cumulative new infections.
  let S = N - DEFAULTS.initialExposed - DEFAULTS.initialInfectious;
  let E = DEFAULTS.initialExposed;
  let I = DEFAULTS.initialInfectious;
  let R = 0;
  let V = 0;
  let F = 0;

  const deriv = (t, s, e, i, r, v) => {
    const beta = beta0 * multiplierAt(segments, t);
    const nu = vaccinationRateAt(vacc, t);
    const inf = (beta * s * i) / N;
    return [
      -inf - nu * s,
      inf - sigma * e,
      sigma * e - gamma * i,
      gamma * i,
      nu * s,
      inf,
    ];
  };

  const sampleCount = Math.round(days) + 1;
  const tArr = new Float64Array(sampleCount);
  const sArr = new Float64Array(sampleCount);
  const eArr = new Float64Array(sampleCount);
  const iArr = new Float64Array(sampleCount);
  const rArr = new Float64Array(sampleCount);
  const vArr = new Float64Array(sampleCount);
  const reffArr = new Float64Array(sampleCount);

  let sample = 0;
  let nextSampleT = 0;
  let t = 0;
  const steps = Math.round(days / dt);
  for (let step = 0; step <= steps; step++) {
    t = step * dt;
    if (t + 1e-9 >= nextSampleT && sample < sampleCount) {
      tArr[sample] = nextSampleT;
      sArr[sample] = S;
      eArr[sample] = E;
      iArr[sample] = I;
      rArr[sample] = R;
      vArr[sample] = V;
      reffArr[sample] = (beta0 * multiplierAt(segments, nextSampleT) * S) / gamma / N;
      sample++;
      nextSampleT = sample;
    }
    if (step === steps) break;
    // Classical RK4 step
    const [ds1, de1, di1, dr1, dv1, df1] = deriv(t, S, E, I, R, V);
    const h2 = dt / 2;
    const [ds2, de2, di2, dr2, dv2, df2] = deriv(
      t + h2, S + h2 * ds1, E + h2 * de1, I + h2 * di1, R + h2 * dr1, V + h2 * dv1,
    );
    const [ds3, de3, di3, dr3, dv3, df3] = deriv(
      t + h2, S + h2 * ds2, E + h2 * de2, I + h2 * di2, R + h2 * dr2, V + h2 * dv2,
    );
    const [ds4, de4, di4, dr4, dv4, df4] = deriv(
      t + dt, S + dt * ds3, E + dt * de3, I + dt * di3, R + dt * dr3, V + dt * dv3,
    );
    S += (dt / 6) * (ds1 + 2 * ds2 + 2 * ds3 + ds4);
    E += (dt / 6) * (de1 + 2 * de2 + 2 * de3 + de4);
    I += (dt / 6) * (di1 + 2 * di2 + 2 * di3 + di4);
    R += (dt / 6) * (dr1 + 2 * dr2 + 2 * dr3 + dr4);
    V += (dt / 6) * (dv1 + 2 * dv2 + 2 * dv3 + dv4);
    F += (dt / 6) * (df1 + 2 * df2 + 2 * df3 + df4);
  }

  // Metrics (day 0..days-1 for capacity days, matching the Python pipeline)
  let peakI = -Infinity;
  let peakDay = 0;
  let daysAbove = 0;
  for (let d = 0; d < sampleCount; d++) {
    if (iArr[d] > peakI) {
      peakI = iArr[d];
      peakDay = d;
    }
    if (d < days && iArr[d] > capacity) daysAbove++;
  }
  const totalInfections = DEFAULTS.initialExposed + DEFAULTS.initialInfectious + F;
  const attackRate = (100 * totalInfections) / N;

  const durationIndex = (() => {
    for (let d = sampleCount - 1; d >= 0; d--) {
      if (iArr[d] >= 1) return Math.min(d + 1, days);
    }
    return 0;
  })();

  return {
    t: tArr, S: sArr, E: eArr, I: iArr, R: rArr, V: vArr, reff: reffArr,
    peakI, peakDay, daysAbove, attackRate, totalInfections,
    durationDays: durationIndex,
    population: N, capacity, days, r0, beta0,
    segments, vacc,
  };
}
