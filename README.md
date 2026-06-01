# Mission Lana: Satellite QKD & Quantum Teleportation Simulator

Quantum-QKD-Aero is a Python R&D sandbox for satellite-to-ground QKD and
teleportation. The Phase 2B physics layer is implemented: the quantities that
drive the simulation are computed from first principles and verified against
analytic results or structural physical properties, rather than drawn or
hardcoded. Parameters (link budget, source quality, sky background) are
**illustrative, not calibrated to a specific instrument** — the physical
relationships and behaviours are the point, not absolute numbers tuned to one
real system.

## Implemented Now

**Quantum information physics (verified):**

- **Teleportation fidelity** computed from the Werner-state resource as
  `F = (1+p)/2`, benchmarked against the classical bound `2/3`. Validated three
  independent ways — analytic, numpy density-matrix, and an optional Qiskit
  density-matrix circuit — which agree to ~1e-9.
- **CHSH / Bell value** `S = 2√2·p`, driven by the *same* Werner parameter as
  teleportation, so the two signals are physically coupled. The regime
  `1/3 < p < 1/√2` (useful for transfer but no Bell violation) is asserted as a
  structural fingerprint.
- **Channel transmittance** computed from a free-space link budget:
  Beer–Lambert atmospheric extinction with `1/sin(elevation)` airmass, and
  Gaussian-beam diffraction capture. The source Werner parameter is kept
  *independent of turbulence* (atmospheric turbulence causes loss, not
  polarisation decoherence) — guarded by a test.
- **Satellite-pass geometry** from a circular orbit and great-circle ground
  track: elevation and slant range are derived and physically coupled (slant
  range at a zenith pass equals the orbit altitude), not independently
  interpolated — guarded by a coupling-proof test.
- **Decoy-state BB84**: Poisson pulse statistics, Lo–Ma–Chen single-photon
  bounds (verified as conservative bounds, with a tightening-limit check), GLLP
  asymptotic secure-key rate.
- **QND / photon-number-splitting eavesdropper**: a hidden-breach attack whose
  QBER-invisibility and decoy-anomaly signature *emerge* from per-photon-number
  behaviour. It keeps QBER at the intrinsic level while raising a decoy anomaly
  and driving the secure-key rate to zero — the canonical attack that a
  QBER-only monitor cannot see but decoy statistics can. Includes an
  intercept-resend strategy as a loud-attack contrast.
- **Background-light coherence model**: effective Werner parameter
  `p_eff = p_source · S/(S+B)` from signal vs. accidental-background coincidence
  rates. Background degrades coherence through the correct mechanism (not via
  turbulence); in daylight, teleportation fidelity arches over a pass and sags
  near the horizon, for a real reason.

**Infrastructure:**

- Local Express dashboard that reads simulator artifacts from `outputs/`.
- Packaging metadata, interface-contract docs, schema recognition, and a pytest
  suite (~95 tests) covering the physics above, including the honesty-guard
  tests noted (turbulence-independence, geometry coupling, decoy bounds,
  PNS-invisible-to-QBER, fidelity arch).

**Note on legacy paths:** earlier "toy" routines (`run_bb84`, the
`TeleportationMission` animation, the `fidelity_noise` curve) are preserved for
backward compatibility but are no longer the basis of the computed physics; some
are slated for removal as the dashboard is rewired to the computed quantities.

## Current Workflow

Run the simulator:

```
python src/qkd/run.py
```

Writes `outputs/results.json` and `outputs/qkd_teleportation.png` (a satellite
pass: channel loss over the pass and the computed teleportation fidelity).

Launch the dashboard:

```
npm start
```

Then open `http://localhost:8080`. The dashboard prefers `outputs/results.json`
and `outputs/qkd_teleportation.png`, falling back to tracked root artifacts.

## Recreate The Python Environment

```
python3 -m venv qkd_env
qkd_env/bin/python -m pip install -r requirements.txt
qkd_env/bin/python src/qkd/run.py
```

For package-style development with the dev extra:

```
python -m pip install -e ".[dev]"
pytest
```

Qiskit is optional (only the teleportation circuit-validation path uses it):

```
python -m pip install -e ".[qiskit]"
```

## Active Code vs Archive

Active code lives in `src/qkd/` (channel, orbit, teleportation, chsh, bb84, eve,
coherence, signals, run), with the dashboard in `dashboard.js` and tests in
`tests/`.

`01-Gate-Noise-Archive/` is preserved archival research material (Bell-state
preparation, noise-model, and measurement-count routines) — potential Qiskit
porting candidates, not part of the active workflow.

Root PNGs and root `results.json` are tracked fallback/demo artifacts; fresh
output is written under `outputs/`.

## Scope & Honesty

Parameters throughout (zenith optical depth, beam divergence, receiver aperture,
source pair-rate, sky background rates, detector efficiency) are representative
illustrative values, **not calibrated to a specific site or instrument**. The
simulator models the correct physical *relationships and behaviours* — how loss
varies over a pass, how a PNS attack hides from QBER, how daylight degrades
coherence — not the absolute performance of any particular real link.
Simplifications are documented in each module (circular orbit, plane-parallel
airmass, asymptotic key rate, simplified accidentals model).

## Planned / Next

- Wire the computed `secure_key_rate` and the daylight fidelity arch into the
  dashboard, retiring the remaining display placeholders.
- Phase 2D: a trust/coherence layer that reads the computed `PhysicsSignals`
  (QBER, decoy anomaly, CHSH/teleportation margins, loss rate, secure-key rate).
- Coherence-enhancement optimisation over the filtering levers exposed in the
  coherence model (window, bandwidth, field of view) vs. signal loss.

`docs/INTERFACES.md` remains the canonical Phase 2 contract; the phase specs in
`docs/` describe the decoy/Eve and background-light work.
