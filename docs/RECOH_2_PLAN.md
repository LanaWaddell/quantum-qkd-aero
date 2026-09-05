# RECOH-2 Plan: Active Rephasing, Ideal Pulse, on the Stored State

**Status:** Implemented and verified against this plan; see the Development
Record (Rev 20) for the certified rung-2 disposition.

**Review record:** Echo reviews `972042011cd0f4af…`, `97a94818b33fb9ce…`,
`85c73c75386b4ae4…`, `7a226e60043be3a8…`; packet confirmation PASS on the
Codex-addressed text (`4eca63e3c67e9167…`). Rev 1.1 re-addressed the packet to
Claude Code (Sonnet). Rev 1.2 resolved an implementer-flagged contradiction
between the RECOH-2 docstring-reconciliation deliverable and RECOH-1's
`test_18` (which froze the PROVISIONAL notice verbatim) via one bounded,
authorized edit to that test (see "RECOH-1 test 18 amendment" below), and
pinned the fidelity report contract to explicit read times. Closure
disposition: PASS, implemented as specified in rev 1.2.

## Scope and claim (binding)

RECOH-2 attempts to earn **rung 2, mechanism `ACTIVE_REPHASING`**, on this
claim only:

> On the single-qubit reference model — a stored qubit with initial Bloch
> vector `r0` (reference `|+>`), zero-mean stationary Gaussian frequency
> noise with Ornstein-Uhlenbeck kernel, no deterministic precession (rotating
> frame), and an ideal instantaneous pi-pulse about the storage-basis X axis
> at predeclared `tau` — the noise-averaged reduced state's `C_l1(t)`
> decreases under free evolution and, after the pulse, increases to a
> predicted echo maximum exceeding the matched free comparator at the
> predeclared read times. The recovered fraction is reported. Nothing is
> conditioned.

Holds for `D_phi > 0` and `C0 > 0`; certified for the reference `|+>`.
"Noise-averaged" means the reduced single-qubit state averaged over noise
realizations; this is intrinsic to the claim, not an ensemble-memory claim.

**Not claimed:** environmental backflow; rung 2 for ensemble/platform
memories; finite-pulse behaviour; key rate.

**ADR-0003 §6 (A1) conditions, discharged:** (a) Bloch vector is complete for
the single-qubit claim, stated no wider; (b) witness `C_l1`, loss-then-
increase; same measure and (absent) conditioning on both trajectories;
matched free comparator constructed from the model; `ACTIVE_REPHASING`
typed, backflow tested zero; recoherence label supported by the coherence-
sensitive witness plus the purity identity guard. Fidelity is reported and
never labels.

## Physics conventions

Noise `<xi(t)xi(0)> = sigma^2 e^{-|t|/tau_c}`, `D_phi = sigma^2*tau_c`,
attenuation `W(t) = exp(-Var(t)/2)`, `C0 = sqrt(rx0^2 + ry0^2)`,
`C_l1(t) = W(t)*C0`.

**State map** (primary object; history-aware by construction):

```
t < tau :  r(t) = ( W_free(t)*rx0,   W_free(t)*ry0,   rz0 )
t >= tau:  r(t) = ( W_ctrl(t)*rx0,  -W_ctrl(t)*ry0,  -rz0 )   # pulse (rx,ry,rz) -> (rx,-ry,-rz); r(tau) = r(tau+)
```

`C_l1` and purity are continuous through `tau`; `ry`, `rz` flip sign. Never
restart independent dephasing from `r(tau)`; never apply a coherence
multiplier > 1 to a state. For `controlled=False` the free state is
`(W_free*rx0, W_free*ry0, rz0)` at every time, with no sign flips; for
`controlled=True` and `t < tau` the controlled variance equals the free
variance; the echo formula is never evaluated with negative `b`.

**Variances.** `g(x) = x - 1 + e^{-x}` (RECOH-1 `_g_ou`); `E(x) = -expm1(-x)`.

`Var_free(t) = 2*D_phi*tau_c * g(t/tau_c)`.

`Var_ctrl(t) = 2*D_phi*tau_c * F(a, b)`, `a = tau/tau_c`, `b = (t-tau)/tau_c`,
`F(a,b) = [h(2a) + h(2b) + Delta^2]/2`, `Delta = exp(-min(a,b))*E(|a-b|)`,
`h(x) = x - 3 + 4e^{-x/2} - e^{-x} = sum_{n>=3} c_n x^n`,
`c_n = (-1)^n (2^{2-n} - 1)/n!` (c3 = 1/12, c4 = -1/32, c5 = 7/960). All terms
of `F` are nonnegative. `F(a,a) = h(2a)`. Hahn law at `2*tau`:
`Var_ctrl(2*tau) = 2*D_phi*tau_c*h(2*tau/tau_c)`.

Peak: `t_peak = tau + tau_c*log1p(E(tau/tau_c))`; small ratio
`2*tau - tau^2/tau_c + O(tau^3/tau_c^2)`; large ratio `-> tau + tau_c*ln(2)`.
The right-derivative of `Var_ctrl` at `tau` is negative for all positive
parameters (a possibly tiny revival always exists for finite OU).

**Lindblad / white kernel** (`tau_c = None`): `W_free = W_ctrl = exp(-D_phi*t)`,
`Cov = 0`, no post-pulse peak. Constructed only via the white kernel, never
via small positive `tau_c`.

**Purity guard.** `P = (1 + |r|^2)/2`; under transverse factor `kappa`,
`P_after - P_before = -(1 - |kappa|^2)(rx^2 + ry^2)/2`: non-increasing,
strictly decreasing iff `|kappa| < 1` and `rx^2 + ry^2 > 0`. In this model
`rz^2` is constant, so `P(t) = [1 + rz0^2 + C_l1(t)^2]/2` exactly on both
trajectories. Model-consistency guard, not an independent mechanism witness.

**Reference numbers** (`D_phi=1, tau_c=2, tau=3, r0=|+>`): `t_peak = 4.1497066`;
`C_free(t_peak) = 0.0906403`, `C_ctrl(t_peak) = 0.3526683`,
`R_peak = 0.2881456`; `C_free(2*tau) = 0.0165797`, `C_ctrl(2*tau) = 0.1853578`,
`R_2tau = 0.1716236`.

## Numerical evaluator

`echo_h(x)`: `x < 0` raises. `x == 0.0` returns `0.0` before any loop. For
`0 < x < 0.5`: series with the general term above; underflow exit — if the
leading term `c3*x^3` rounds to `0.0`, return `0.0` immediately; otherwise
accumulate and stop when `|term| < 1e-17*|sum|` or a term rounds to `0.0`
after a nonzero sum exists (return the sum); defensive cap of 60 iterations
raises `RuntimeError`. For `x >= 0.5`: direct form
`x - 3 + 4*exp(-x/2) - exp(-x)`.

`echo_F(a,b)`: the identity above; `F(0,0) == 0.0` exactly; `Delta` via
`exp(-min)*E(|a-b|)`. Single path: `stored_state_at -> var_free/var_ctrl ->
echo_h/echo_F`. Asserted invariants: `Var >= 0`, `0 <= W <= 1`,
`|r| <= 1 + 1e-12`. Every scalar physical input (`t`, `tau`, `tau_c`,
`D_phi`, Bloch components) is validated finite real, and every storage time
`t >= 0`; NaN, +/-inf, and negative times raise `ValueError` naming the
parameter, for scalars and arrays alike.

**Tolerance policy.** Positive representable references: stated relative
target and `est > 0`; no absolute floor. Exact analytic zeros: `== 0.0`.
Underflow domain: references below `1e-300` carry no relative-accuracy claim
(finiteness and `>= 0` only). Mixed tolerance is used only for O(1)
trajectory quantities (`C`, purity, states), stated as absolute agreement of
bounded quantities. Independent reference: Python `decimal` at >= 50 digits
(70 for the `F` cases).

## Report contract

`recovery_report(model, n_grid)` constructs both trajectories from
`EchoModel` (matching by construction). `recovery_status in {available,
no_loss, no_peak, unresolved_loss}` with `reason`. Precedence, in order:

1. `C0 == 0` -> `no_loss` ("zero initial transverse coherence"); recovery
   fields `None`.
2. `D_phi == 0` -> `no_loss` ("zero noise intensity"); recovery fields
   `None`.
3. white kernel -> `no_peak`; `t_peak = None`; `R_2tau = 0.0` analytic
   (helper not called); `recovery_class = NONE`. This branch takes priority
   over the numerical loss-resolution check; weak white noise therefore
   reports `no_peak`, tested.
4. OU: at each requested read time (`t_peak`, `2*tau`), if
   `|C0 - C_free(t_r)| <= 1e-12` -> `unresolved_loss` naming the read time,
   recovery fields `None`, helper not called; else `available`.

Fields: `recovery_status, reason, recovery_class, valid, t_peak, R_peak,
R_2tau, C_free_peak, C_ctrl_peak, backflow_free, purity_guard, fidelity`.
`valid` is `True` iff `purity_guard.status == passed` and the comparator was
model-constructed (always true here, since `recovery_report` always
constructs both trajectories from the same `EchoModel` before branching).
Read times are evaluated exactly from the analytic map (no interpolation).
`backflow_free` is the grid-resolved positive variation of `D(t) = W_free(t)`
for the named pair `{|+>, |->}`.

`fidelity` is a mapping evaluated at every defined read time: key `"2tau"`
always (the controlled state exists on every branch; fidelity is independent
of loss resolution), key `"t_peak"` only when `t_peak` is defined. Each value
is `pure_target_fidelity(r_ctrl(t_r), r0)` when `|r0| = 1` within `1e-9`,
else the string `"not_available"`. Reported only; never labels; no
mixed-state fidelity is introduced. For `|+>`,
`fidelity["2tau"] == (1 + C_ctrl(2*tau))/2` (the pure-dephasing identity).

`recovery_fraction(C0, C_free_tr, C_ctrl_tr) = (C_ctrl_tr - C_free_tr)/(C0 -
C_free_tr)`, raising `ValueError` if `|C0 - C_free_tr| <= 1e-12` (direct
callers only). `purity_guard(states_free, states_ctrl, rz0) -> GuardResult`:
both `None` -> `not_evaluated`; exactly one `None` -> `ValueError`; both
present -> check the identity at every state to `1e-12`. `echo_grid(model,
n)`: `[0, 2*tau]`, `n >= 8`, uniform interior plus exact insertion of `tau`
and (when defined) `t_peak`; strictly increasing, deduplicated.
`evolve(model, t_grid, controlled)` validates `t_grid` (finite, strictly
increasing, no duplicates). Unconditioned by construction: no branch on
outcomes, no acceptance rule, no weighting anywhere in the path. No RNG.

## RECOH-1 test 18 amendment

RECOH-1's `test_18` asserted, verbatim, that both module docstrings contain
"Configuration names in this module are PROVISIONAL pending the memory SPEC
amendment (RECOH-0 v0.2 §4); reconciliation is a RECOH-2 obligation." That
sentence declared its own expiry: the SPEC is ratified (`81c97ed`) and this
packet is the named reconciliation, so a frozen test asserting the
PROVISIONAL marker's continued presence would block the very step it names.
Rev 1.2 authorized exactly one edit to an existing test: the `notice` string
constant in `test_18` was replaced with the ratified-SPEC notice, and the
test renamed to `test_18_import_hygiene_and_ratified_spec_notice`. No other
line of `tests/test_recoh1.py` changed; the test count stayed at 25; the
import-hygiene half of the test is unchanged.

Ratified notice (verbatim, in both module docstrings): "Configuration names
in this module (`dephasing_model`, `noise_kernel`, `D_phi`, `tau_c`) follow
SPEC-memory-lifetime-adr0003 (ratified 2026-09-03, `81c97ed`); `kappa_ideal`
corresponds to `identity_state_evolution`."

## Proof obligations (39 implemented; ≈36 planned)

State map and pulse (tests 01-05): pulse involution and invariants;
continuity through `tau` with `ry`/`rz` sign flips; non-equatorial witnesses
equal `W*C0`; `evolve` matches `stored_state_at` pointwise; history-unaware
restart from `r(tau)` under-recovers relative to the correct history-aware
trajectory.

Evaluator (tests 06-14): `var_free` matches `_g_ou` scaling; Hahn law at
`2*tau`; `echo_h` series and direct branches against Decimal references
(rel `< 1e-13`/`1e-14`); switch continuity at `x=0.5`; edge cases (`x=0`,
subnormal, underflow policy, no `RuntimeError`); `echo_F` against 70-digit
Decimal; `F(a,a) == h(2a)` bitwise; `F(0,0) == 0.0`; `Var_ctrl` near the peak
against Decimal; exact `t_peak` against grid argmax across `tau/tau_c` in
`{0.1, 1, 5, 20}`; small- and large-ratio asymptotics; right-derivative sign
at `tau`; reference numbers to the packet's quoted precision.

Guard and loophole (tests 15-18): purity identity on both trajectories at
every grid time for `|+>` and a non-equatorial state; purity non-increase
with equality on eigenstate/diagonal-mixed/maximally-mixed and strict
decrease on `|+>`; a synthetic Z-precession-style loophole distinguishing an
F-based witness from `C_l1`; guard `None`-handling and longitudinal-
corruption detection.

Rung-2 test and controls (tests 19-23f): reference report earns
`ACTIVE_REPHASING` with `valid == True` and the reference `R` values; the
Lindblad control reports `no_peak` with `C_ctrl == C_free`; weak white noise
reports `no_peak` ahead of loss resolution; OU-to-Lindblad convergence at
`tau_c = 1e-4` (sampled maxima within the stated bounds) and the small-`tau`
documentation case; `D_phi = 0` and diagonal-state controls report `no_loss`
without exceptions; `unresolved_loss` names the read time without raising;
`recovery_fraction` raises on zero loss; `echo_grid` and `evolve` input
validation.

Hygiene (tests 24-26): both docstrings carry the ratified notice verbatim
and no `PROVISIONAL`; import hygiene and no-RNG AST scan; no herald/
success-probability argument names.

## Out of scope (binding)

Finite pulse duration, angle error, CPMG (RECOH-2b); intrinsic backflow and
RTN (RECOH-3); ensemble or platform memories; key-rate coupling (RECOH-4);
heralded or conditioned recovery; general mixed-state fidelity; SPEC or ADR
edits; Echorym analogues; any change to RECOH-1 tests other than the
authorized `test_18` amendment.
