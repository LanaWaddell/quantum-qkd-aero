# DN — Quasiperiodic misalignment fixture

Status: proposed, rev 5 (rev 5 applies Echo confirm C4: the test docstring
"Golden's normalised discrepancy stays bounded where a badly-approximable
step does not" was self-contradictory — golden is itself the
badly-approximable arm; the contrast is with the *well-approximable*
π-derived step. Rewritten as a finite-comparison statement over the
declared N set {50, 200, 1000, 5000}, and the test renamed
`test_golden_worst_case_discrepancy_is_bounded_over_declared_range`
(Echo's advisory rename adopted, pre-commit, so a finite check cannot be
read as global proof). Docstring/name only — assertions unchanged. Rev 4
applies Echo review A5: the remaining
uncited global discrepancy-optimality claims are narrowed to the
badly-approximable / bounded-type formulation — this note's §1 "tightest
discrepancy bound available to any rotation number" and §4 "Golden
minimises lim sup … over rotation numbers", and their three counterparts in
quasiperiodic.py (module docstring, finite-N paragraph, `star_discrepancy`
docstring). What survives is the citable boundedness statement: the golden
step's continued fraction is all ones, hence badly approximable, hence
`N·D*_N / log N` bounded; minimality among rotation numbers is no longer
asserted anywhere. Docstring/prose only — no behavioral change. Rev 3
applies Echo review R6: remaining stale strings corrected in code/tests — the quasiperiodic.py PDT gloss and "tightest D*_N of any alpha" overclaim, the test file's two §3.3 references, and this note's §7 "§3.3 amendment only" line. Rev 2: Cowork Claude review pass 2026-08-24 — verified against
`6f292d4`: 24/24 tests pass, suite 877+1-skipped no-qiskit, emission hash
unchanged. Rev 2 corrections: (i) the module docstring's "closes after 720
steps" for 137.5° corrected to 144 — 275/2 degrees is 55/144 of a turn, as the
DN, `orbit_period`, and the test already said; (ii) the amendment re-targeted
from §3.3 to **ADR-0003 §4** — the tabulation warrant lives in the honesty
taxonomy (row 1: deterministic exogenous → "Tabulate freely", rationale "smooth
ephemeris"), not in §3.3's composition rules; (iii) the PDT acronym gloss in
the subpackage docstring corrected — PDT here is probability-distribution-of-
transmittance, not "precomputed deterministic table"; the admission-class
bandwidth argument survives intact and §3 below now states it against the
actual implementation.)
Depends on: ADR-0002, ADR-0003 (RATIFIED 2026-07-17), LINK-1, LINK-6b
Proposes: ADR-0003 §4 row-1 clarification (tabulation criterion)
Adds: `src/qkd/fixtures/` (new subpackage), `tests/test_quasiperiodic_fixture.py`

## 1. What this is, and what it is not

This note introduces a synthetic misalignment schedule driven by an
irrational rotation of the circle, defaulting to the golden angle. It
models no physics. Free-space propagation imposes no golden-angle rotation
on a polarization or time-bin reference frame, and the numerical proximity
of 137.5077° to the inverse fine-structure constant is a coincidence of
units with no physical content. The fixture is filed under a new
`src/qkd/fixtures/` subpackage rather than extended into `qkd.effects`
precisely so that the physics library never acquires a member whose
justification is aesthetic.

The reason to build it anyway is that the physical effect library cannot
generate the input class it produces. Physical misalignment drift is smooth
and slow; a seeded random walk is unstructured. A quasiperiodic schedule is
neither — reproducible from a single scalar, non-repeating over any
practical horizon, and, its rotation number being badly approximable
(continued fraction all ones), equidistributing with bounded-type
discrepancy (`N·D*_N / log N` bounded in N). That combination is a useful
adversarial
input for estimator and monitor assumptions, and it is the only kind of
input for which the tabulation question below can be posed cleanly.

## 2. Composition

`QuasiperiodicMisalignmentFixture` is a third `misalignment_error` owner
alongside `PolarizationMisalignmentEffect` and `PhaseMisalignmentEffect`.
The LINK-1 single-contributor rule applies unchanged and is tested. The
emitted value is

    misalignment_error = sin²( A · sin(2π · {φ₀ + n·α}) ),   n = t / T,  α = step_deg / 360

The outer `sin²` is the same time-bin phase-error mapping the physical
phase owner discharges. The inner bounded sine is what makes the excursion
quasiperiodic while holding `δφ` inside the small-angle model: without that
ceiling a wrapped phase would emit out-of-model errors that still land in
[0, 1] and pass validation silently. `A = 0` emits bit-exact identity, so
the fixture is inert unless deliberately armed.

`step_deg` remains a free constructor parameter. The fixture is a
discriminator between rotation numbers, not an argument for one, and the
acceptance tests run √2- and π-derived steps plus a rational step as
comparison arms.

The fixture declares no controls, consumes no RNG, and reads nothing
outside `(t, geom)`. The ADR-0002 wall is untouched, which matters more
here than usual: this thing will be pointed at estimators.

## 3. Proposed ADR-0003 §4 row-1 clarification (rev 2 re-aim)

ADR-0003 §4 (the honesty taxonomy) licenses tabulation for the
deterministic-exogenous tier — "Tabulate freely" — with the rationale "smooth
ephemeris; interpolation error controllable and quantifiable". The rationale
already carries a smoothness assumption; the rule as stated does not. In the
implementation the same warrant surfaces twice: `PDT_ADMISSIBLE_EFFECTS`'
`deterministic` class (evaluated once per profile sample, then treated as
constant across the block's `n_pulses`), and any future table-backed provider.
A deterministic signal whose variation is *not* resolved by the evaluation
grid breaks both — the block statistic uses the sample-instant value where the
physics delivers the block mean of a nonlinear map, which is precisely the
mean-collapse ADR-0003 forbids for stochastic fading, arriving by a
deterministic route. The stated justification is
nonlinearity: bin-averaging transmittance overestimates key rate because
gain and QBER are nonlinear in T. That justification does not actually
depend on stochasticity, and this fixture is the counterexample that shows
it.

`test_coarse_grid_biases_a_fully_deterministic_signal` evaluates a signal
that is deterministic, bounded, smooth, and RNG-free, on a coarse stride,
and recovers a **−12.7% relative bias** on the mean misalignment error at
stride 55, amplitude 0.3 rad. The bias grows monotonically across strides
13, 21, 55 — Fibonacci denominators, which are the best rational
approximants to the golden rotation number and therefore the strides that
resonate hardest with it. Determinism conferred no protection whatsoever.

Proposed clarification (a warrant sharpening of §4 row 1, membership
unchanged — arguably making the row's own rationale binding rather than
changing the decision): **tabulation safety is a claim about the signal's
bandwidth relative to the evaluation grid, not about whether the signal is
deterministic.** An effect is PDT-admissible when its variation
is resolved by the grid it will be evaluated on. Determinism remains
necessary — a stochastic effect is inadmissible regardless — but it stops
being sufficient.

The existing allowlist survives this amendment unchanged in membership:
every current `deterministic` member is either constant or slowly varying
over a pass. The amendment changes the *warrant*, not the roster, and adds
an explicit criterion for future additions. `PDT_ADMISSIBLE_EFFECTS`
remains a closed-world allowlist keyed by `effect_id`; the binding
subpackage rule is that no `fixture_`-prefixed id may ever be added to it,
and that is tested.

## 4. What a golden step can and cannot show

This section exists because the fixture's provenance is a social-media post
proposing that golden-angle rotations produce distinctive quantum
behaviour. The question is answerable, and the answer is partly negative.

**Cannot show: any steady-state difference.** The orbit `{n·α}` is
Weyl-equidistributed for every irrational α, so every observable depending
only on the invariant measure — long-run mean misalignment error,
asymptotic key rate — has the same limit for all irrational steps.
Measured at N = 200,000, golden, √2-derived, and e-derived steps agree to
3 × 10⁻⁸. A run reporting a steady-state golden-angle advantage has a bug.
This is pinned as `test_ergodic_limit_is_step_independent`.

**Cannot show: pointwise optimality.** The bounded-type property is a
worst-case-over-N statement — `N·D*_N / log N` stays bounded — not a claim
about any particular N. At N = 5000 the √2 step is measurably
*more* uniform. Pinned as `test_golden_is_not_pointwise_optimal`, so a
later run cannot reinterpret one favourable N as a general win.

**Can show: bounded worst-case finite-N structure.** Taking the supremum of
`N·D*_N / log N` over N ∈ {50, 200, 1000, 5000} gives 0.42 for the golden
step and 4.65 for the π-derived step, because π admits the strong rational
approximation 22/7 and its orbit clusters. That is the real discriminator,
and it is a statement about how well a rotation number is approximable by
rationals — not about φ having special status in nature.

**Can show: gap structure.** At most three distinct gap lengths for any
rotation orbit, verified as a structural check that the fixture is a
rotation and not an ad-hoc waveform.

## 5. The rational-literal confound

`137.5°` is 55/144 of a turn. Its orbit closes after 144 steps and the
float orbit tracks that closure to ~10⁻¹⁴ over n ≤ 500. A rounded "golden
angle" literal is therefore a short-period signal wearing quasiperiodic
clothing, and any study that rounds its step angle for convenience has
silently switched experiments. `orbit_period()` reports the closure period
under exact-decimal semantics, and
`test_rational_step_recurs_and_irrational_step_does_not` pins the
distinction. A separate test asserts run lengths stay far below the
IEEE-754 closure horizon, where every step is a dyadic rational and every
orbit eventually closes.

## 6. Acceptance

24 tests, all passing; full suite 877 passed / 1 skipped, no regressions.
Three are labelled load-bearing null results and exist specifically to make
an over-claim fail loudly: step-independent ergodic limit, absence of
pointwise optimality, and non-admissibility for tabulation.

## 7. Not in scope

No production-stack membership. No `effect_id` allowlist entry. No claim
that any real link exhibits quasiperiodic misalignment. No estimator
change: this note proposes the fixture and the §4 row-1 clarification only, and any
consumption of the fixture by an estimator would go through the ordinary
consumption gate.
