"""qkd.mem0_gundogan -- MEM-0: analytic finite-key reconstruction of the
Gündoğan et al. 2-QM time-delayed single-satellite repeater benchmark.

Canonical numerical source (MEM-0 plan v1.2 §"Canonical numerical source"):
    M. Gündoğan, J. S. Sidhu, M. Krutzik, D. K. L. Oi, "Time-delayed single
    satellite quantum repeater node for global quantum communications,"
    Optica Quantum 2(3), 140-147 (2024), DOI 10.1364/OPTICAQ.517495.
    (arXiv:2303.04174v2 is a cross-check source only.)

Scope statement (binding, plan §7): this module independently RECONSTRUCTS the
published finite-key calculation under explicitly stated assumptions.  It
evaluates agreement with reported benchmark behaviour and does not validate
the physical model, hardware feasibility, or Quantum-QKD-Aero performance.

Reconstruction assumptions (plan §9, predeclared before any evaluation):
  E1  f_e = 1.0 (Shannon-limit idealization; the source omits f_e).
      Sensitivity sweep {1.0, 1.1, 1.16, 1.19, 1.22} reported in the
      benchmark artifact for every binding anchor.
  E2  log base 2 in both finite-size concentration terms of Eq. (1)
      (h is binary entropy, base 2, throughout).

Count-model derivation trail (plan §3.6; per-factor citations):
  2-QM conceptual form:  n_Z + n_X = p_basis * p_BSM * min(M_A, M_B),
      M_k = s*T*P_click(eta_arm_k)   [paper Fig. 1(c),(d): QM1 modes retained
      on A-side ground click; B-side successes paired and swapped].
  Identical-pass reduction (MEM-0 matched assumption; asymmetric passes out
  of scope -- do NOT reuse the reduced form for asymmetric passes):
      n_Z + n_X = (1/4)*s*T*P_click(eta_arm)   [paper Sec. 4: N = 4(n_Z+n_X),
      factor (a) 50% basis mismatch, factor (b) 50% BSM success].
  1-QM:  n_Z + n_X = (1/2)*s*T*P_click(eta_A)*P_click(eta_B)  [paper Sec. 2:
      no BSM in the 1-QM scheme; per-trial AND-structure across the two
      passes gives the stated eta_ch^2 key-length scaling].
  Arm efficiencies (plan §3.4): 2-QM eta_arm = eta_ch*eta_det*eta_mem on both
  arms (one memory per arm: QM1/A, QM2/B; App. A definition of eta).  1-QM is
  physically asymmetric (partner stored, later retrieved and sent to B):
      eta_A = eta_ch*eta_det;  eta_B = eta_ch*eta_det*eta_mem.
  These readings are predeclared; acceptance anchors TEST them, and an anchor
  failure triggers discrepancy review, never an interpretation switch.

Units contract (plan §3.1): the public API takes channel loss in dB
(`channel_loss_db`); linear transmissivity is derived internally and every
linear variable carries the `_linear` suffix.

Import hygiene (plan §3): standard library + NumPy only; never imports the
LINK pipeline, qkd.fixtures, qkd.adaptive, qkd.hybrid, or qkd.canonical.
Pure functions; no RNG; no I/O; frozen reference parameters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

__all__ = [
    "Mem0Params",
    "TABLE1",
    "F_E_SENSITIVITY_SET",
    "binary_entropy",
    "p_d_nominal",
    "alpha_real_click",
    "p_click",
    "scheme_arms",
    "counts",
    "qbers",
    "finite_key",
    "asymptotic_rate",
    "evaluate",
    "loss_cutoff_db",
    "crossover_db",
    "p_d_cutoff",
]

# --------------------------------------------------------------------------
# Frozen reference parameters (published Table 1; plan §3.2)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Mem0Params:
    """Published Table 1 parameter set (frozen literals; plan §3.2)."""

    s: float = 5e6              # EPS rate, pairs/s
    T: float = 240.0            # transmission period per ground station, s
    eps_sec: float = 5e-12      # secrecy parameter
    eps_corr: float = 5e-12     # correctness parameter
    p_n: float = 1e-3           # memory noise probability (per storage trial)
    p_bg: float = 6.4e-7        # background count probability
    p_dc: float = 1e-7          # detector dark count probability
    tau_window: float = 200e-9  # temporal window, s (documentary; not used)
    eta_mem: float = 0.6        # combined memory write-in/read-out efficiency
    eta_det: float = 0.8        # detection efficiency
    delta_imbalance: float = 0.02   # detector imbalance (Delta in Eq. 1)
    lambda_bsm: float = 0.98    # BSM ideality (2-QM only)
    eps_m: float = 0.02         # misalignment error incl. source infidelity
    p_bsm: float = 0.5          # BSM success probability (2-QM only)
    f_e: float = 1.0            # E1 reconstruction assumption (Shannon limit)


TABLE1 = Mem0Params()

#: E1 sensitivity set (plan §9); the benchmark artifact reports every binding
#: anchor across this set.
F_E_SENSITIVITY_SET = (1.0, 1.1, 1.16, 1.19, 1.22)

_LOG2_CONC = True  # E2 reconstruction assumption: base-2 concentration terms


# --------------------------------------------------------------------------
# Primitives (plan §3.3, §3.7)
# --------------------------------------------------------------------------


def binary_entropy(q: float) -> float:
    """Binary entropy h(q), base 2, defined on [0, 1] only (plan §3.7).

    Raises ValueError outside [0, 1]; callers enforce the security-domain
    rules (q_ph >= 1/2 -> zero key) *before* calling.
    """
    if q < 0.0 or q > 1.0:
        raise ValueError(f"binary_entropy domain violation: q={q}")
    if q == 0.0 or q == 1.0:
        return 0.0
    return -q * math.log2(q) - (1.0 - q) * math.log2(1.0 - q)


def eta_ch_linear_from_db(channel_loss_db: float) -> float:
    """Units contract (plan §3.1): dB loss -> linear transmissivity."""
    return 10.0 ** (-channel_loss_db / 10.0)


def p_d_nominal(channel_loss_db: float, params: Mem0Params = TABLE1) -> float:
    """Nominal total incoherent-click probability (published App. A):
    p_d = eta_ch_linear*p_n + p_bg + p_dc."""
    eta_ch_linear = eta_ch_linear_from_db(channel_loss_db)
    return eta_ch_linear * params.p_n + params.p_bg + params.p_dc


def alpha_real_click(eta: float, p_d: float) -> float:
    """Published Eq. (A1): probability of a *real* detection event."""
    return eta * (1.0 - p_d) / (1.0 - (1.0 - eta) * (1.0 - p_d) ** 2)


def p_click(eta: float, p_d: float) -> float:
    """Any-click (herald) probability: the denominator of Eq. (A1) --
    the paper's own click structure (plan §3.3)."""
    return 1.0 - (1.0 - eta) * (1.0 - p_d) ** 2


# --------------------------------------------------------------------------
# Scheme structure (plan §3.4-§3.6)
# --------------------------------------------------------------------------


def scheme_arms(scheme: str, channel_loss_db: float,
                params: Mem0Params = TABLE1) -> tuple[float, float]:
    """Per-arm end-to-end efficiencies (eta_A_linear, eta_B_linear).

    2-QM: one memory per arm (QM1/A, QM2/B)  -> eta_ch*eta_det*eta_mem each.
    1-QM: memory on the B arm only (stored, later retrieved and sent to B)
          -> eta_A = eta_ch*eta_det;  eta_B = eta_ch*eta_det*eta_mem.
    Predeclared readings; anchors test, never select (plan §3.4).
    """
    eta_ch_linear = eta_ch_linear_from_db(channel_loss_db)
    base = eta_ch_linear * params.eta_det
    if scheme == "2QM":
        return base * params.eta_mem, base * params.eta_mem
    if scheme == "1QM":
        return base, base * params.eta_mem
    raise ValueError(f"unknown scheme: {scheme!r}")


def counts(scheme: str, channel_loss_db: float,
           params: Mem0Params = TABLE1,
           p_d_total: float | None = None,
           block_scale: float = 1.0) -> tuple[float, float]:
    """(n_Z, n_X) per the predeclared count model (plan §3.6).

    `p_d_total` is the Fig. 3(c) benchmark-mode override (plan §3.3): a pure
    function argument replacing the nominal p_d; Table-1 defaults are never
    mutated.  `block_scale` multiplies s*T for the A8 asymptotic-consistency
    check only.
    """
    p_d = p_d_nominal(channel_loss_db, params) if p_d_total is None else p_d_total
    eta_a, eta_b = scheme_arms(scheme, channel_loss_db, params)
    trials = params.s * params.T * block_scale
    if scheme == "2QM":
        # Conceptual: p_basis * p_BSM * min(M_A, M_B); identical passes ->
        m = trials * p_click(eta_a, p_d)
        n_total = 0.5 * params.p_bsm * m          # = (1/4) * s*T*P_click
    else:  # 1QM
        n_total = 0.5 * trials * p_click(eta_a, p_d) * p_click(eta_b, p_d)
    n_z = n_x = n_total / 2.0                     # symmetric basis choice
    return n_z, n_x


def qbers(scheme: str, channel_loss_db: float,
          e_m: float,
          params: Mem0Params = TABLE1,
          p_d_total: float | None = None) -> tuple[float, float]:
    """(e_X, e_Z) per published Eqs. (A3)-(A6), reproduced as printed.

    NOTE (ledger L4): the published 1-QM e_X, Eq. (A5), carries NO
    1/2*[1-alpha_A*alpha_B] floor term, unlike Eq. (A6) for e_Z.  Both the
    published article and arXiv v2 print it this way; it is reproduced
    verbatim and never symmetrized.
    """
    p_d = p_d_nominal(channel_loss_db, params) if p_d_total is None else p_d_total
    eta_a, eta_b = scheme_arms(scheme, channel_loss_db, params)
    a_a = alpha_real_click(eta_a, p_d)
    a_b = alpha_real_click(eta_b, p_d)
    em, epsm = e_m, params.eps_m
    if scheme == "2QM":
        lam = params.lambda_bsm
        eps_dp = 2.0 * em * (1.0 - em)            # Eq. (A2), e_m1 = e_m2
        core = lam * a_a * a_b
        e_x = core * (epsm * (1.0 - eps_dp) + eps_dp * (1.0 - epsm)) \
            + 0.5 * (1.0 - core)                  # Eq. (A3)
        e_z = core * epsm + 0.5 * (1.0 - core)    # Eq. (A4)
    else:
        core = a_a * a_b
        e_x = core * (epsm * (1.0 - em) + em * (1.0 - epsm))  # Eq. (A5), as printed
        e_z = core * epsm + 0.5 * (1.0 - core)                # Eq. (A6)
    return e_x, e_z


# --------------------------------------------------------------------------
# Finite key (published Eq. (1); both bases explicit -- plan §3.7)
# --------------------------------------------------------------------------


def _concentration(n_same: float, n_other: float, eps_sec: float) -> float:
    """delta(n_same, n_other) = sqrt((n_same+1)*log2(1/eps_sec) /
    (2*n_other*(n_other+n_same)))  [E2: base-2]."""
    log_term = math.log2(1.0 / eps_sec) if _LOG2_CONC else math.log(1.0 / eps_sec)
    return math.sqrt((n_same + 1.0) * log_term / (2.0 * n_other * (n_other + n_same)))


def _basis_key(n_same: float, n_other: float, e_phase: float, e_bit: float,
               params: Mem0Params) -> tuple[float, bool]:
    """One basis of Eq. (1).  Returns (key length clamped >= 0, domain_flag).

    Security-domain contract (plan §3.7): if the phase-error upper bound
    q_ph >= 1/2, or q_ph falls outside [0, 1], the basis contributes ZERO
    key (domain_flag True in the out-of-[0,1] case).
    """
    if n_same <= 0.0 or n_other <= 0.0:
        return 0.0, False
    q_ph = (e_phase + _concentration(n_same, n_other, params.eps_sec)) \
        / (1.0 - params.delta_imbalance)
    if q_ph < 0.0 or q_ph > 1.0:
        return 0.0, True
    if q_ph >= 0.5:
        return 0.0, False
    log_term = (math.log2 if _LOG2_CONC else math.log)(
        2.0 / (params.eps_corr * params.eps_sec ** 2))
    length = n_same * (1.0
                       - binary_entropy(q_ph)
                       - params.f_e * binary_entropy(e_bit)
                       - params.delta_imbalance) - log_term
    return max(length, 0.0), False


def finite_key(scheme: str, channel_loss_db: float, e_m: float,
               params: Mem0Params = TABLE1,
               p_d_total: float | None = None,
               block_scale: float = 1.0) -> dict:
    """Full evaluation record: n_Z, n_X, e_X, e_Z, L_Z, L_X, L, R, flags."""
    n_z, n_x = counts(scheme, channel_loss_db, params, p_d_total, block_scale)
    e_x, e_z = qbers(scheme, channel_loss_db, e_m, params, p_d_total)
    # Z basis: phase estimated from e_X; EC leakage f_e*h(e_Z)   [Eq. (1)]
    l_z, flag_z = _basis_key(n_z, n_x, e_x, e_z, params)
    # X basis: roles exchanged in BOTH terms                     [plan §3.7]
    l_x, flag_x = _basis_key(n_x, n_z, e_z, e_x, params)
    l_total = l_z + l_x
    n_pairs = n_z + n_x
    return {
        "scheme": scheme, "channel_loss_db": channel_loss_db, "e_m": e_m,
        "n_Z": n_z, "n_X": n_x, "e_X": e_x, "e_Z": e_z,
        "L_Z": l_z, "L_X": l_x, "L": l_total,
        "R": (l_total / n_pairs) if n_pairs > 0.0 else 0.0,
        "domain_flag": flag_z or flag_x,
    }


def asymptotic_rate(scheme: str, channel_loss_db: float, e_m: float,
                    params: Mem0Params = TABLE1,
                    p_d_total: float | None = None) -> float:
    """n -> infinity limit of the implemented per-pair rate (plan §3.7):
    concentration term -> 0; the Delta structure of Eq. (1) is retained.
    Used by A8 (internal consistency) and A9 (report-only)."""
    e_x, e_z = qbers(scheme, channel_loss_db, e_m, params, p_d_total)
    total = 0.0
    for e_phase, e_bit in ((e_x, e_z), (e_z, e_x)):
        q_ph = e_phase / (1.0 - params.delta_imbalance)
        if 0.0 <= q_ph < 0.5:
            r = 1.0 - binary_entropy(q_ph) \
                - params.f_e * binary_entropy(e_bit) - params.delta_imbalance
            total += max(r, 0.0)
    return total / 2.0  # per pair (each pair contributes to one basis)


def evaluate(scheme: str, channel_loss_db: float, e_m: float,
             params: Mem0Params = TABLE1,
             p_d_total: float | None = None) -> dict:
    """Convenience wrapper: finite record + asymptotic per-pair rate."""
    rec = finite_key(scheme, channel_loss_db, e_m, params, p_d_total)
    rec["R_asymptotic"] = asymptotic_rate(scheme, channel_loss_db, e_m,
                                          params, p_d_total)
    return rec


# --------------------------------------------------------------------------
# Cutoff and crossover location (plan §3.7; bisection to 0.01 dB)
# --------------------------------------------------------------------------


def _bisect(pred, lo: float, hi: float, tol: float) -> float:
    """Largest x in [lo, hi] with pred(x) True; pred(lo) must be True and
    pred(hi) False."""
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if pred(mid):
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def loss_cutoff_db(scheme: str, e_m: float, params: Mem0Params = TABLE1,
                   lo: float = 10.0, hi: float = 60.0,
                   tol: float = 0.01, asymptotic: bool = False) -> float:
    """Largest channel_loss_db with positive key (L > 0 finite; rate > 0
    asymptotic)."""
    if asymptotic:
        def pred(db):
            return asymptotic_rate(scheme, db, e_m, params) > 0.0
    else:
        def pred(db):
            return finite_key(scheme, db, e_m, params)["L"] > 0.0
    if not pred(lo):
        raise ValueError("no positive key at lower bracket")
    if pred(hi):
        raise ValueError("positive key at upper bracket; widen bracket")
    return _bisect(pred, lo, hi, tol)


def crossover_db(e_m: float, params: Mem0Params = TABLE1,
                 lo: float = 15.0, hi: float = 28.0,
                 tol: float = 0.01) -> float:
    """A4 quantity: channel_loss_db where finite R_1QM - R_2QM changes sign
    (Fig. 3(a)); 1-QM leads at low loss under the predeclared model."""
    def diff(db):
        r1 = finite_key("1QM", db, e_m, params)["R"]
        r2 = finite_key("2QM", db, e_m, params)["R"]
        return r1 - r2
    d_lo, d_hi = diff(lo), diff(hi)
    if d_lo == 0.0:
        return lo
    if (d_lo > 0) == (d_hi > 0):
        raise ValueError(f"no sign change in [{lo},{hi}] dB: {d_lo}, {d_hi}")
    return _bisect(lambda db: (diff(db) > 0) == (d_lo > 0), lo, hi, tol)


def p_d_cutoff(scheme: str, channel_loss_db: float, e_m: float,
               params: Mem0Params = TABLE1,
               lo: float = 1e-7, hi: float = 1e-2,
               tol_factor: float = 1.001) -> float:
    """A7 quantity: largest swept p_d_total with L > 0 at fixed loss
    (Fig. 3(c) reconstruction); log-domain bisection."""
    def pred(pd):
        return finite_key(scheme, channel_loss_db, e_m, params,
                          p_d_total=pd)["L"] > 0.0
    if not pred(lo):
        raise ValueError("no positive key at lower p_d bracket")
    if pred(hi):
        raise ValueError("positive key at upper p_d bracket; widen bracket")
    llo, lhi = math.log(lo), math.log(hi)
    while lhi - llo > math.log(tol_factor):
        mid = 0.5 * (llo + lhi)
        if pred(math.exp(mid)):
            llo = mid
        else:
            lhi = mid
    return math.exp(0.5 * (llo + lhi))


def with_f_e(params: Mem0Params, f_e: float) -> Mem0Params:
    """Sensitivity-sweep helper (E1): a copy with f_e replaced; the frozen
    TABLE1 instance is never mutated."""
    return replace(params, f_e=f_e)
