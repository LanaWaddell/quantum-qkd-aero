# ML4QT 2026 — Experiment 1: is adapting worth it?

Poster presented at the ML4QT Symposium, Institute for Quantum Computing,
University of Waterloo, 24 September 2026 (`ML4QT2026_poster_Waddell.pdf`).

**Provenance.** Everything in this folder is experiment scaffolding that lives
*above* the physics wall (ADR-0002). It imports the repository's decoy-state
BB84 functions unchanged and modifies nothing under `src/qkd/`. Channel
parameters are ILLUSTRATIVE — representative, not calibrated to any instrument.
Results are SIMULATED and PRELIMINARY. The run was made against the repository
at the 970/991-test state quoted on the poster; the physics functions it
imports are unchanged since.

## Question

When a satellite link drifts under orbital geometry, turbulence, and weather, is
it worth letting a controller adapt its settings, or is a well-chosen fixed
setting better?

## What was run

- **Channel generator** (`agent.py: make_pass`): deterministic orbital-pass link
  budget (elevation → airmass extinction and diffraction capture),
  Ornstein–Uhlenbeck fading in log η (correlation time ≈ 8 s), and a two-state
  Markov cloud process (×0.03 while cloudy). One pass = 600 s at 0.5 s steps.
- **Reward** (`agent.py: block_key`): certified secure key per block, from the
  repository's `_honest_gain`, `_honest_qber`, `estimate_decoy_bounds`, and
  `secure_key_rate`, evaluated at the conservative edge of Poisson-sampled
  counts (Z = 3). This finite-count penalty is a confidence-interval
  *heuristic* added here so that block length has a physical cost; it is not a
  finite-key security proof.
- **Learner**: discounted Gaussian Thompson sampling over 20 arms (signal
  intensity μ ∈ {0.2, 0.35, 0.5, 0.7, 0.9} × block length ∈ {5, 10, 20, 40} s)
  and 9 contexts (elevation band × previous block's certified-key band),
  forgetting factor 0.995. Trained on 100 passes, scored on the next 30.
- **Baselines**: a static setting (best single arm on five cloud-free passes:
  μ = 0.7, 40 s blocks); a memoryless per-block re-optimiser (fixed 20 s
  blocks, μ chosen for the η implied by the last block); and a *myopic* oracle
  that sees the true η for the coming block only.
- **Sweep**: source rate 1e8, 1e7, 1e6, 1e5 pulses/s (bright → 1000× dimmer).

## Result — share of the static setting's key, mean over the 30 scored passes

| source rate (pulses/s) | myopic oracle | reactive, no memory | learner |
|---|---|---|---|
| 1e8 | 0.996 | 0.995 | 0.894 |
| 1e7 | 0.987 | 0.962 | 0.901 |
| 1e6 | 0.963 | 0.776 | 0.837 |
| 1e5 | 0.915 | 0.253 | 0.729 |

Nothing beat the static setting. The reactive controller collapsed at low count
rates because it reacts to estimator noise. The learner was more stable than
the reactive controller but never overcame the cost of frequent adjustment.
Even the myopic oracle lost at low count rates, because choosing block by block
forfeits the count accumulation that long blocks provide.

Reading: for intensity and block length under honest weather, there was nothing
worth adapting. The next study exposes decisions a fixed setting cannot make —
abstaining during a fade, and responding to a photon-number-splitting
eavesdropper (already modelled in `src/qkd/eve.py`) whose signature the decoy
statistics carry.

## Caveats, as stated on the poster

- The oracle is myopic (one block ahead), not a dynamic-programming oracle.
- The finite-count penalty is a heuristic, not a finite-key proof.
- The channel generator is uncalibrated; validation against recorded free-space
  link data is the next step.
- The static setting was tuned on clear-sky passes of this same channel. The
  learner had 100 training passes, so the comparison is fair, but a real
  deployment would not get a clean rehearsal.

## Reproduce

```
pip install -e .              # from the repository root
cd experiments/ml4qt-2026
for r in 1e8 1e7 1e6 1e5; do PULSE_RATE=$r python agent.py; done   # ~4 min each
python results_fig.py         # figures/results.svg from results/*.json
python figs.py                # figures/hero.svg and variance.svg
```

`results/agent_results_<rate>.json` holds the per-pass learning curves for all
four controllers and one block-by-block evaluation pass. The figure scripts use
TeX Gyre fonts; any sans-serif substitutes cleanly.

## Research horizon, as presented on the poster

1. **Adaptive link** (current) — when should one changing link adapt, and when
   should it stay put?
2. **Multi-node network** (next) — how should nodes coordinate routes and
   limited resources when none sees the whole system?
3. **Heterogeneous networking** (future) — how can control work across fibre,
   free-space, and satellite segments without hiding their differences?
4. **Quantum internetworking** (long-term) — how can distinct networks
   coordinate end to end, as parts of a future quantum internet?

The remaining adaptive-link experiments (value of each observable; sabotage vs
weather; silent regime change; learned commitment timing) are specified in the
project's architecture documents and will be added here as they are run.
