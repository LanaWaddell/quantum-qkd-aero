# Phase 2B-5 — Background Light → werner_p (SPEC)

**Status:** specification, queued. Self-contained for a fresh session.
**Relationship:** extends 2B-2 (`channel_state`) and 2B-3 (the pass loop). Realises
the `# TODO(2B background-light)` marker left in `channel.py`. Implement AFTER 2B-4
or independently; it does not depend on decoy/Eve.
**One-line purpose:** make `werner_p` depend on conditions through the *correct*
physical mechanism — background-light contamination — NOT through turbulence.

---

## 0. Why this exists, and the trap it must avoid

2B-2 deliberately made `werner_p` independent of the weather, because for
polarisation-encoded QKD atmospheric turbulence causes LOSS, not depolarisation.
That was the honest first cut, and its guard test
(`turbulence changes eta but NOT werner_p`) must STILL PASS after this phase.

But there IS a real mechanism by which conditions degrade the entangled-state
quality: **background light**. Stray photons (sky radiance, strongest in daylight)
fall within the detector's time/frequency/spatial acceptance window and register
as uncorrelated "coincidences." These uncorrelated events mix an incoherent
(white-noise) component into the measured two-photon state — which is exactly a
reduction of the Werner parameter.

THE TRAP (the analogue of the sine curve / the decorative `p`): do NOT reintroduce
`werner_p = f(weather_quality)` as a smooth hand-wave. `werner_p` must degrade as a
function of **background count rate B** and **signal coincidence rate S**, both of
which have physical definitions. "Daylight" is an input to B, never a direct knob
on `p`. Turbulence still only touches `eta` (hence S), and only changes `p`
*through* the S/(S+B) ratio — never directly. The 2B-2 guard test stays valid
because that test holds B fixed/zero.

---

## 1. The physics (what to implement, and what each term means)

### 1.1 The contamination model
Let:
  - `S` = true signal coincidence rate — the rate of genuine entangled-pair
    detections. `S ∝ eta` (the channel transmittance from `channel_state`) times
    the source pair-emission rate and detector efficiencies. So S is HIGH near
    peak elevation, LOW at the horizon.
  - `B` = background coincidence rate — accidental coincidences from stray photons
    and dark counts within the coincidence window. `B` depends on sky radiance
    (day/night), the detector time-window `Δt`, the optical bandwidth, and the
    field of view. It does NOT depend on the entanglement source quality.

The fraction of detected coincidences that are genuine signal is `S / (S + B)`.
The background admixture is white (unpolarised, uncorrelated) → it adds a
maximally-mixed component. So the **effective Werner parameter**:

    werner_p_effective = p_source * S / (S + B)

where `p_source` is the intrinsic source quality (the current `werner_p`,
i.e. visibility of the source with zero background). When B → 0 (night, tight
filtering), `werner_p_effective → p_source` (recovers 2B-2 behaviour). When B
becomes comparable to S (bright sky, low signal), `werner_p_effective` sags.

(A common equivalent formulation uses the signal-to-background ratio
`SBR = S/B`: `werner_p_effective = p_source * SBR / (SBR + 1)`. Either form is
fine; state which.)

### 1.2 The honest, elegant consequence (the 2B-5 payoff)
Because `S ∝ eta`, and `eta` is worst at low elevation (long slant range, high
airmass), the signal-to-background ratio is WORST at the horizon and BEST at peak
elevation. Therefore `werner_p_effective` — and hence teleportation fidelity —
now **varies over the pass**: it sags near the horizon and peaks at closest
approach. The flat fidelity line from 2B-3 becomes a gentle arch, FOR A REAL
REASON. This is the headline visible result of 2B-5.

This must be a *consequence* of the S/(S+B) physics, not a curve fitted to look
arched. If fidelity-over-pass is ever produced by anything other than the
computed effective Werner parameter, the phase has failed its standard.

### 1.3 Modelling B
Keep B's model honest-but-simple, parameterised, and flagged as illustrative (as
2B-2's link-budget params were):

    B ≈ R_bg * Δt          (accidental-coincidence floor)

where `R_bg` is a background singles rate (counts/s) set by an input like
`sky_condition` ∈ {night, twilight, day} mapping to representative radiance
levels, and `Δt` is the coincidence window. Document that the absolute numbers are
representative, not calibrated to a specific site/instrument. The SHAPE (p sags
when S/B drops) is the honest part; the absolute B is illustrative.

---

## 2. Interface targets

Extend `channel_state` (or add a helper it calls) WITHOUT breaking its signature
or the 2B-2 guard test. Suggested:

- Add optional background parameters to the `atmosphere`/config dict (or a new
  `environment` arg): `sky_condition` or explicit `background_rate_hz`,
  `coincidence_window_s`, plus a `source_pair_rate_hz` and the detector efficiency
  needed to turn `eta` into `S`.
- Compute `werner_p_effective` from `p_source` (the existing `werner_p` config,
  now interpreted as the *source* value) and the S/(S+B) ratio.
- `ChannelState.werner_p` becomes the EFFECTIVE value. (If both are useful, the
  source value can be carried separately, but `werner_p` in the dataclass should
  be the effective one that downstream teleportation_fidelity consumes — that is
  what makes the pass fidelity arch.)
- DEFAULT background → night / negligible B, so the DEFAULT behaviour reproduces
  2B-2 exactly (and the 2B-2 guard test passes unchanged).

`p_override` must still force a fixed werner_p (bypassing the background model),
for tests and sweeps.

---

## 3. Test targets

Replace nothing existing must regress. Add:

1. **Zero background recovers 2B-2:** with night/`B=0`, `werner_p == p_source`
   exactly (so `test_turbulence_changes_eta_but_not_werner_p` still holds — that
   test uses default/zero background).
2. **Background degrades p:** higher `B` (day vs night) at fixed geometry →
   strictly lower `werner_p_effective`.
3. **THE GUARD (preserved):** with B held fixed, varying `zenith_optical_depth`
   changes `eta` but `werner_p_effective` changes ONLY through S(eta) — assert that
   with B = 0 it does not change at all, and with B > 0 it changes in the correct
   direction (more loss → lower S → lower S/(S+B) → lower p). This refines, not
   contradicts, the 2B-2 guard.
4. **Pass arch:** over a `satellite_pass`, with B > 0, `werner_p_effective` peaks
   at max elevation and sags at the horizon (because S tracks eta). Hence
   teleportation fidelity over the pass is no longer flat — assert it varies and
   peaks at closest approach.
5. **Filtering restores p (sets up the Echorym story):** reducing the coincidence
   window `Δt` (tighter temporal filtering) lowers B and raises
   `werner_p_effective` — assert monotonic. (See §5.)
6. **Bounds:** `0 <= werner_p_effective <= p_source <= 1` always.
7. **Override bypasses model:** `p_override` forces the value regardless of B.

Test #4 is the visible payoff; test #3 is the honesty guard that proves we did
NOT just couple p to weather directly.

---

## 4. Scope discipline

**In scope:** the S/(S+B) effective-Werner model, background parameterisation,
making fidelity vary over the pass as a consequence, the tests above, updating the
2B-3 plot/JSON so fidelity-over-pass is shown honestly (it is now a curve, not a
constant line — update the run.py plot accordingly).

**Out of scope:**
- trust/coherence (2D);
- making turbulence *directly* depolarise (it must not — only via S);
- detector spectral models beyond the simple Δt/bandwidth floor (flag as future);
- v2.0 schema switch unless done deliberately with the hardening (same note as 2B-4).

---

## 5. Echorym alignment (captured here so the intent survives the session)

This phase is where "coherence degraded by environment" first appears in real
physics. But the user's actual interest is the COMPLEMENT: how coherence can be
*protected and restored* under noisy conditions, not merely how it decays.

2B-5 sets up exactly that substrate. The honest ways to RAISE `werner_p_effective`
against a bright background are real QKD techniques that reduce B:
  - tighter temporal filtering (smaller coincidence window Δt),
  - narrower spectral filtering (smaller optical bandwidth),
  - smaller field of view / better spatial-mode matching,
  - adaptive optics (also raises eta → raises S).
Each has a trade-off (tighter filtering can also reduce S if mismatched), so
"achieving optimal coherence despite noisy conditions" becomes a genuine,
computable optimisation: maximise `werner_p_effective` (or secure key rate, once
2B-4 lands) over the filtering parameters, subject to the S-vs-B trade-off.

That optimisation — coherence *enhancement under uncertainty* — is the bridge from
this physics layer to the Echorym systems-level question. It is a LATER phase
(2D / Echorym), not 2B-5. 2B-5 only builds the honest substrate on which it can be
posed. Do not implement the optimisation here; just leave the levers (Δt,
bandwidth, FOV) exposed and documented so the later work has real knobs to turn.
