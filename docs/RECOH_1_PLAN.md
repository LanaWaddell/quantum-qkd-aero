# RECOH-1 Plan — Stored-State and Dephasing Reference Instrument

**Status:** v1.1 — PI-approved MEM-0-style execution with provisional names.
**Date:** 2026-09-03
**Review record:** v1.1 — Echo plan review 2026-09-03 (approve with four packet-level
corrections); PI approved MEM-0-style execution with provisional names.
**Governing records:** RECOH-0 v0.2 (ratified for Plan drafting 2026-09-03;
Echo round-2 refinements incorporated: derived `recovery_class`, RTN analytic
continuation, egg-info as separate follow-up); ADR-0003 §3.6, §6; SPEC-memory-
lifetime-adr0003 §1 (three-quantity decomposition); MEM-0 plan (standalone-
module pattern).
**Lane:** RECOH-* (research/validation lane consuming — and in this packet
*creating* — the first stored-state primitive beside MEM). Baseline:
main @ `215a876`, 945 no-Qiskit-file / 966 full-env (Rev 18.1 baseline,
reverified before source edits).
**Commit shape:** four files — `src/qkd/mem_state.py`, `src/qkd/recoh.py`,
`tests/test_recoh1.py`, `docs/RECOH_1_PLAN.md` — plus the Development Record
reconciled in the same commit. No other source, test, configuration, SPEC,
ADR, README, or schema changes.

**Provenance.** This is plan v1 with C1–C4, R-a/R-b, and the composition test
folded in, plus execution-packet rev 2's explicit Choi convention and validation
split. Source snapshots: `claude_RECOH-1-plan.md` SHA-256
`c654ba43abed1e6d708980068e15cdf8add1b2dbbc12e753f7108bc1d78b835b`;
`codex-packet-RECOH-1.md` rev 2, after the PI-approved explanatory typo
correction, SHA-256 `eab6c4b7f7284821242d7710072d3c473ca221032b058e98c5419a79e9ec89cc`.
The OU series' leading relative truncation error is `x³/60`, approximately
`1.67e-11` at `x = 1e-3`, not the superseded `x/120 ≈ 1e-5`. This changes
the explanation only, not the prescribed series, switch, or acceptance tolerance.

**Execution authority.** Codex modifies only the five authorized files, runs
tests and verification commands, and reports results. Codex does not stage,
commit, amend, push, tag, merge, rebase, or perform any repository-history or
remote write. Lana performs all staging, commits, and pushes. References to
the commit/push below describe the state Lana creates after review.

---

## 1. Claim scope

RECOH-1 is **instrument calibration**. It adds an explicit stored qubit state
and three analytic pure-dephasing maps, plus the derived witnesses that later
packets will use. It makes **no rung-2 claim**: on every free-evolution model in
this packet the classifier returns `NONE`, and a test asserts that. The
ADR-0003 §6 capability status remains **planned**. No RNG, trajectories,
control pulses (RECOH-2), intrinsic-backflow model (RECOH-3), key-rate coupling
(RECOH-4), retrieval-efficiency model, or change to any emission path.

**Sequencing disposition.** RECOH-1 introduces no SPEC field and touches no
MEM document. The PI approved the standalone MEM-0-style ordering, with local
configuration names provisional until SPEC reconciliation in RECOH-2, rather
than waiting for Gates A/B1/C. Gate A (Echo MEM-basis review) remains open.
Gate B0 is **YES** (PI, 2026-09-03). This permission to build an instrument
does not ratify an age-dependent memory capability or alter ADR §6.

Both module docstrings contain this statement verbatim:

> Configuration names in this module are PROVISIONAL pending the memory SPEC
> amendment (RECOH-0 v0.2 §4); reconciliation is a RECOH-2 obligation.

## 2. Physics conventions

**State.** Bloch vector `r ∈ ℝ³`, `ρ = (I + r·σ)/2`. `StoredQubit(rx, ry, rz)`
is a frozen dataclass. Finite components and `|r| ≤ 1 + 1e-12` are validated
without renormalization; each error names the offending quantity. `PLUS` and
`MINUS` denote `(1,0,0)` and `(-1,0,0)`. `density_matrix(state)` returns the
2×2 complex density matrix.

**Pure-dephasing map.** `dephase(state, kappa)` maps `(rx, ry)` to
`κ·(rx, ry)` and leaves `rz` unchanged. It rejects nonfinite κ and `|κ| > 1`.
The equivalent Kraus map is `(1+κ)/2 · ρ + (1−κ)/2 · ZρZ`. Negative κ is
admitted at the map level for the later RECOH-3 candidate; RECOH-1's analytic
free-evolution models all produce κ in `[0,1]`.

**Choi convention (rev 2).** `choi_dephasing(kappa)` returns the unnormalized
`J = Σ_ij E(|i⟩⟨j|) ⊗ |i⟩⟨j|`, in output-first basis
`|00⟩,|01⟩,|10⟩,|11⟩`:

```text
[[1, 0, 0, κ],
 [0, 0, 0, 0],
 [0, 0, 0, 0],
 [κ, 0, 0, 1]]
```

Its eigenvalues are `1+κ, 1−κ, 0, 0`, total trace is 2, and output partial
trace is `I`. The constructor accepts **any finite real κ**, including
nonphysical `|κ| > 1`, for diagnosis. It does not share `dephase`'s
physicality validation. `is_cptp_dephasing(kappa)` checks Choi PSD
(minimum eigenvalue ≥ −1e-12) and output partial trace `I` (absolute 1e-12,
zero relative tolerance); thus a value such as 1.01 returns `False`, not an
exception. This numerical tolerance is not permission for `dephase` to
accept values above its strict `|κ| ≤ 1` bound.

**Models (analytic, no RNG).** Configuration labels remain local/provisional.

| `dephasing_model` | κ(t) | Parameters |
|---|---|---|
| `ideal` | 1 | — |
| `lindblad_phase_damping` | `exp(−D_phi·t)` | `D_phi` [1/s] |
| `gaussian_frequency_noise`, `noise_kernel=white` | same `kappa_lindblad` call | `D_phi` |
| `gaussian_frequency_noise`, `noise_kernel=ornstein_uhlenbeck` | `exp[−D_phi·tau_c·g(t/tau_c)]` | `D_phi`, `tau_c` |

Convention: frequency noise ξ(t), `⟨ξ(t)ξ(0)⟩ = σ² e^{−|t|/τc}`,
`κ = exp(−½⟨φ²⟩)`, and **white-limit-safe intensity** `D_phi = σ²·tau_c`.
`σ² = D_phi/tau_c` is derived, never configured. `T2 = 1/D_phi` is a
reporting alias only (infinite at zero rate). `constant_error` (AFC/REID,
e_m constant) remains a distinct MEM quantity, absent here.

**R1 identity.** `kappa_gaussian(t, D_phi, tau_c=None)` directly returns
`kappa_lindblad(t, D_phi)` through the same code path, not a separate formula.

**R-a stability.** Private `_g_ou(x)` evaluates `g(x) = x−1+e^{-x}` with
`x + np.expm1(-x)` for `x ≥ x_switch` and `x²/2−x³/6+x⁴/24` below
`x_switch = 1e-3`. The corrected leading relative error of the series is
`x³/60`; the switch is continuous to absolute 1e-12. Tests probe the helper
directly, including a high-precision small-x comparison, and check its use
by the production OU function.

**R-b domains.** Finite `t ≥ 0` (arrays allowed; any negative element
rejects), finite `D_phi ≥ 0` (zero is ideal), and finite **`tau_c > 0`** for
OU. Non-positive tau rejects, even when the rate is zero; white noise is
represented by `None`, not by a finite-tau call with zero. Validation errors
name the parameter. Scalar inputs return scalar factors; time arrays retain
their shape.

**Derived witnesses (`recoh.py`; outputs, never inputs).**

- `coherence_l1(state) = 2|ρ₀₁| = √(rx²+ry²)`.
- **C2:** `pure_target_fidelity(state, target)` requires `|r_target| = 1`
  within absolute 1e-9, else `ValueError("target must be pure")`. Returns
  `(1+r·r_target)/2`, the squared-overlap pure-target convention, not general
  mixed-state fidelity. For `PLUS` under dephasing it equals `(1+κ)/2`.
- `trace_distance(a, b) = ½‖r_a−r_b‖₂`.
- **C3:** `trace_distance_backflow(D, t)` is `Σ max(D[i+1]−D[i], 0)`.
  Its docstring states: "Discrete BLP-type backflow for a PRESELECTED
  reference state pair; this function does NOT perform the BLP maximization
  over initial states, and the result is grid-resolved (a revival between
  samples is not detected)." Equal lengths, finite 1-D data, strictly
  increasing t, and `D ∈ [−1e-12, 1+1e-12]` are required. In this experiment
  the free pair is `PLUS, MINUS`; their Bloch difference `(2κ,0,0)` gives
  `D(t) = |κ(t)|`. No time-step weighting is applied to positive increments.
- **C4:** `recovery_fraction(C0, C_free_tr, C_ctrl_tr, *, tol=1e-12)` returns
  `(C_ctrl_tr−C_free_tr)/(C0−C_free_tr)` without clamping. If
  `|C0−C_free_tr| ≤ tol`, raise
  `ValueError("recovery fraction undefined: no recoverable coherence loss occurred")`;
  never substitute zero or NaN for that undefined case.
- **C1:** `classify_recovery(t, C_free, C_ctrl=None, *, backflow=None, tol=1e-9)`
  returns `RecoveryClass` with enum members `NONE`, `PROTECTION_ONLY`,
  `ACTIVE_REPHASING`, `ENVIRONMENTAL_BACKFLOW`. A qualifying revival means
  indices `i<j<k` satisfying `C[j] < C[i]−tol` and `C[k] > C[j]+tol`.
  Apply these rules in order:
  1. `ENVIRONMENTAL_BACKFLOW` iff free coherence has a qualifying revival
     and supplied `backflow > tol`.
  2. `ACTIVE_REPHASING` iff controlled coherence has a qualifying revival
     and free coherence does not.
  3. `PROTECTION_ONLY` iff controlled coherence is supplied, neither series
     has a qualifying revival, and `C_ctrl[-1] > C_free[-1]+tol`.
  4. Otherwise `NONE`.
  Validate equal lengths, strictly increasing t, and finite values. Endpoint
  improvement alone is never a recoherence label. There is no `t_r` API.

## 3. Standalone module boundary

`mem_state.py`: `StoredQubit`, `PLUS`, `MINUS`, `density_matrix`, `dephase`,
`choi_dephasing`, `is_cptp_dephasing`, `kappa_ideal`, `kappa_lindblad`, and
`kappa_gaussian`, with the private stable `_g_ou` helper.
`recoh.py`: the derived witnesses and classifier above. Its only
project-internal dependency is the new `qkd.mem_state` state type.

Both use only the standard library and NumPy beyond that local dependency.
Prohibited in both: `qkd.effects`, `qkd.link`, `qkd.adaptive`, `qkd.hybrid`,
`qkd.fixtures`, `qkd.mission`, `qkd.schema`, `qkd.mem0_gundogan`,
`numpy.random`, and `random`. No I/O, seeds, streams, event simulation,
controls, or coupling to production. No package registration edit is needed.

## 4. Proof obligations (`tests/test_recoh1.py`; planned +25)

1. Density matrices after dephasing remain Hermitian, trace-one, and PSD
   for κ in `{−1, −0.5, 0, 0.5, 1}`.
2. Choi eigenvalues, unnormalized trace, output partial trace, and CPTP
   checks agree with the κ bound; `dephase(_, 1.01)` raises naming it.
3. `rz` and density-matrix populations are invariant.
4. `D_phi=0` gives κ=1 for Lindblad and OU, including array inputs.
5. R1 white-kernel/Lindblad identity to 1e-12, with the shared code path checked.
6. Fixed-D white limit: `|κ_OU−exp(−Dt)| < 1e-3` at `tau_c=1e-3/D`,
   `t ∈ [0,5/D]`. Wrong fixed-σ² limit also tested: with `D=σ² tau_c`,
   `κ_OU(1/σ) > 0.999` at `tau_c=1e-3/σ`, approaching 1 as tau shrinks.
7. Short-time Gaussian asymptote through `_g_ou`:
   `|κ_OU/exp(−Dt²/(2 tau_c))−1| < 1e-3` for `t/tau_c ≤ 1e-2`.
   The ratio approaches 1 from above; the absolute-error criterion is binding.
8. Long-time `−ln(κ_OU)/(Dt)` within 1e-2 of 1 at `t/tau_c=200`.
9. OU monotone non-increase on a 10⁴-point grid; folded 9b checks
   `|series−expm1 form| < 1e-12` at the `1e-3` switch.
10. L1 coherence is 1 for PLUS and `|κ|` after dephasing.
11. Pure-target fidelity of dephased PLUS is `(1+κ)/2`; mixed target rejects.
12. Antipodal-pair trace distance is 1 initially and `|κ|` after dephasing both.
13. Free Lindblad and OU evolution produce zero trace-distance backflow.
14. Synthetic nonmonotone D produces positive backflow, not a physical-model
    claim; folded 14b tests lengths, time order, finiteness, and D bounds.
15. Every RECOH-1 free model with no control classifies as NONE.
16. Synthetic classifier checks cover all categories, precedence, plateau
    revivals, and absence of environmental classification without backflow.
17. Endpoint-only improvement is protection, never recoherence; folded 17b
    checks undefined recovery fraction and the exact unclamped ratio.
18. AST import hygiene and the provisional-name docstrings; bare module imports
    do not load `qkd.effects`.
19. No `numpy.random`/`random` or equivalent RNG API references.
20. Unchanged production emission and schema extension registry; run.py keeps
    `Min loss 27.7 dB | Fidelity 0.990`, existing in-process parity tests pass.
    The registry has two containing-section entries, read from `215a876`,
    not guessed. Tests use temporary output directories.
21. Negative/nonfinite D_phi rejects with the parameter named.
22. Non-positive tau_c rejects (both 0 and −1), also at zero rate.
23. Negative/nonfinite time rejects, including an invalid element in an array.
24. Out-of-ball or nonfinite Bloch components reject with the quantity named.
25. Added composition test: `dephase(dephase(ρ, κ₁), κ₂)` agrees with
    `dephase(ρ, κ₁κ₂)` to 1e-12 over `{−0.9, −0.3, 0, 0.4, 1}²`.

## 5. Out of scope

Hahn/CPMG or any control sequence (RECOH-2); RTN or any nonmonotone physical
κ model (RECOH-3); stochastic trajectories, seeds, or streams; retrieval
efficiency and `constant_error`; general mixed-state fidelity; BLP
maximization over initial states; a read-time `t_r` API; SPEC/ADR text
changes; Gündoğan/Paterson coupling; any Echorym-side analogue; egg-info
untracking. The later RTN reference note must state that for `v > γ`,
`μ = √(γ²−v²)` is imaginary and the hyperbolic expression analytically
continues to `cos/sin`.

## 6. Verification and Development Record reconciliation

Run `qkd_env/bin/python -m pytest -q --ignore=tests/test_teleportation_qiskit.py`
(expected 970 = 945+25), and the full suite with the Qiskit extra (expected
991 = 966+25). Report actual counts and any mismatch; do not tune the count.
Run `qkd_env/bin/python src/qkd/run.py`, the bare module import check, and
`git diff --check`. Status must show exactly the four additions plus the
Development Record; no egg-info change or Git staging/history/remote write.

Codex reconciles `docs/Quantum-QKD-Aero_Development_Record.md` written
**forward** — true as of the push that includes it; describe completed phases
as complete, not pending push. **Omit the commit hash**; Claude's post-push
verification adds it. Counts come from actual runs, with and without the
Qiskit-specific file, with delta +25/+25 compared to 945/966 flagged if it
differs. Preserve history in dated Correction Log entries, never overwrite
superseded numbers; each current-state fact appears once in the body, with
superseded statements only in the log.

Rev 19 states: RECOH-1 is an **instrument**; `RecoveryClass` is a **derived
output**; configuration names are **provisional** until the memory SPEC
amendment; rung-2 capability is **unchanged (planned)**; Gate A remains open;
Gate B0 is **YES** (PI, 2026-09-03).
