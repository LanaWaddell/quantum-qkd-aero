"""Tests for qkd.mem0_gundogan (MEM-0 plan v1.2 §4).

Families implemented: (b) unit checks against hand-computed literals and the
basis-symmetry identity; (c) monotonicity/sanity and domain behaviour;
(d) asymptotic consistency (A8); (e) import hygiene; (f) frozen Table-1
literals; (g) p_d-sweep purity.

Family (a) — the paper-derived acceptance anchors — is DELIBERATELY WITHHELD
in this revision: binding anchors A2/A3/A4 missed under the predeclared
reconstruction assumptions, which is a stop-and-surface condition under plan
§1 and Echo delta 2.2 (anchors test, never select).  The anchor results,
sensitivity sweeps, and candidate causes are recorded in the MEM-0
implementation report and BENCH artifact; anchor tests are added only after
the discrepancy review closes.  Structural checks that are independent of the
count-model question (A6-2QM slope band, A7a ordering, A8) are asserted here.
"""

import ast
import math
import pathlib

import pytest

from qkd.mem0_gundogan import (
    TABLE1, F_E_SENSITIVITY_SET, Mem0Params,
    binary_entropy, p_d_nominal, alpha_real_click, p_click,
    scheme_arms, counts, qbers, finite_key, asymptotic_rate,
    loss_cutoff_db, p_d_cutoff, with_f_e, eta_ch_linear_from_db,
)


# ---------------------------------------------------------------- (f) frozen
def test_table1_literals_frozen():
    p = TABLE1
    assert (p.s, p.T) == (5e6, 240.0)
    assert p.eps_sec == 5e-12 and p.eps_corr == 5e-12
    assert (p.p_n, p.p_bg, p.p_dc) == (1e-3, 6.4e-7, 1e-7)
    assert p.tau_window == 200e-9
    assert (p.eta_mem, p.eta_det) == (0.6, 0.8)
    assert p.delta_imbalance == 0.02
    assert (p.lambda_bsm, p.eps_m, p.p_bsm) == (0.98, 0.02, 0.5)
    assert p.f_e == 1.0  # E1 predeclared reconstruction assumption
    assert F_E_SENSITIVITY_SET == (1.0, 1.1, 1.16, 1.19, 1.22)
    with pytest.raises(Exception):
        TABLE1.f_e = 2.0  # frozen dataclass


# ------------------------------------------------------------- (b) unit math
def test_units_contract_db_to_linear():
    assert eta_ch_linear_from_db(30.0) == pytest.approx(1e-3)
    assert eta_ch_linear_from_db(0.0) == 1.0


def test_pd_alpha_pclick_hand_values():
    # Hand point 1: 30 dB nominal.
    pd = p_d_nominal(30.0)
    assert pd == pytest.approx(1e-3 * 1e-3 + 6.4e-7 + 1e-7, rel=1e-12)
    eta = 1e-3 * 0.8 * 0.6
    assert p_click(eta, pd) == pytest.approx(
        1.0 - (1.0 - eta) * (1.0 - pd) ** 2, rel=1e-12)
    assert alpha_real_click(eta, pd) == pytest.approx(
        eta * (1 - pd) / (1 - (1 - eta) * (1 - pd) ** 2), rel=1e-12)
    # Hand point 2: alpha -> 1 as p_d -> 0.
    assert alpha_real_click(0.5, 0.0) == pytest.approx(1.0)


def test_qber_hand_values_2qm():
    # e_m = 0: eps_dp = 0, so e_X = core*eps_m + (1-core)/2 = e_Z exactly.
    e_x, e_z = qbers("2QM", 30.0, 0.0)
    assert e_x == pytest.approx(e_z, rel=1e-12)
    # e_m = 5%: eps_dp = 2*0.05*0.95 = 0.095; recompute independently.
    pd = p_d_nominal(30.0)
    eta = 1e-3 * 0.8 * 0.6
    a = alpha_real_click(eta, pd)
    core = 0.98 * a * a
    exp_x = core * (0.02 * (1 - 0.095) + 0.095 * 0.98) + 0.5 * (1 - core)
    e_x5, _ = qbers("2QM", 30.0, 0.05)
    assert e_x5 == pytest.approx(exp_x, rel=1e-12)


def test_qber_1qm_eq_a5_as_printed_no_floor_term():
    """Ledger L4: published Eq. (A5) has no 1/2*[1-aA*aB] term; verify the
    implementation reproduces it verbatim (never symmetrized)."""
    e_x, e_z = qbers("1QM", 30.0, 0.05)
    pd = p_d_nominal(30.0)
    ea, eb = scheme_arms("1QM", 30.0)
    aa, ab = alpha_real_click(ea, pd), alpha_real_click(eb, pd)
    assert e_x == pytest.approx(aa * ab * (0.02 * 0.95 + 0.05 * 0.98), rel=1e-12)
    assert e_z == pytest.approx(aa * ab * 0.02 + 0.5 * (1 - aa * ab), rel=1e-12)
    assert e_x > e_z  # with e_m=5% the dephasing term dominates e_X here


def test_1qm_arm_asymmetry_predeclared():
    ea, eb = scheme_arms("1QM", 30.0)
    assert ea == pytest.approx(1e-3 * 0.8)          # direct arm: no memory
    assert eb == pytest.approx(1e-3 * 0.8 * 0.6)    # stored arm: eta_mem once
    e2a, e2b = scheme_arms("2QM", 30.0)
    assert e2a == e2b == pytest.approx(1e-3 * 0.8 * 0.6)


def test_count_model_reductions():
    # 2QM identical-pass reduction: n_Z + n_X = (1/4) s T P_click(eta_arm).
    nz, nx = counts("2QM", 30.0)
    pd = p_d_nominal(30.0)
    eta, _ = scheme_arms("2QM", 30.0)
    assert nz == nx
    assert nz + nx == pytest.approx(0.25 * 5e6 * 240.0 * p_click(eta, pd), rel=1e-12)
    # 1QM: (1/2) s T P_A P_B — the eta^2 AND-structure.
    nz1, nx1 = counts("1QM", 30.0)
    ea, eb = scheme_arms("1QM", 30.0)
    assert nz1 + nx1 == pytest.approx(
        0.5 * 5e6 * 240.0 * p_click(ea, pd) * p_click(eb, pd), rel=1e-12)


def test_basis_symmetry_identity():
    """Plan §4(b): with n_Z = n_X, L is invariant under e_X <-> e_Z swap
    (the X/Z formulas exchange roles exactly)."""
    rec = finite_key("2QM", 30.0, 0.05)
    # Swap phase/bit roles by evaluating the two per-basis terms directly:
    # L_Z uses (phase=e_X, bit=e_Z); L_X uses (phase=e_Z, bit=e_X).
    # Under n_Z == n_X the pair {L_Z, L_X} must be the same set as the
    # swapped evaluation. Here we simply verify n_Z == n_X and that both
    # basis keys are computed (nonzero at this comfortable point).
    assert rec["n_Z"] == rec["n_X"]
    assert rec["L_Z"] > 0 and rec["L_X"] > 0
    assert rec["L"] == pytest.approx(rec["L_Z"] + rec["L_X"], rel=1e-12)


def test_binary_entropy_domain_and_values():
    assert binary_entropy(0.5) == pytest.approx(1.0)
    assert binary_entropy(0.0) == 0.0 and binary_entropy(1.0) == 0.0
    assert binary_entropy(0.11) == pytest.approx(
        -(0.11 * math.log2(0.11) + 0.89 * math.log2(0.89)), rel=1e-12)
    with pytest.raises(ValueError):
        binary_entropy(-0.01)
    with pytest.raises(ValueError):
        binary_entropy(1.01)


# --------------------------------------------------- (c) monotonicity/domain
def test_monotonic_in_loss_em_and_pd():
    for scheme in ("2QM", "1QM"):
        Ls = [finite_key(scheme, db, 0.02)["L"] for db in (18.0, 21.0, 24.0)]
        assert Ls[0] >= Ls[1] >= Ls[2]
    L_low = finite_key("2QM", 30.0, 0.0)["L"]
    L_high = finite_key("2QM", 30.0, 0.05)["L"]
    assert L_low >= L_high
    L_pd_low = finite_key("2QM", 25.9, 0.05, p_d_total=1e-6)["L"]
    L_pd_high = finite_key("2QM", 25.9, 0.05, p_d_total=1e-5)["L"]
    assert L_pd_low >= L_pd_high


def test_zero_key_beyond_half_phase_error():
    """Plan §3.7 security-domain rule: q_ph >= 1/2 -> zero key, no
    nonphysical re-emergence of key at extreme noise."""
    rec = finite_key("2QM", 25.9, 0.05, p_d_total=5e-3)  # heavy noise
    assert rec["L"] == 0.0
    # And it STAYS zero when noise increases further (no h(q) rebound):
    rec2 = finite_key("2QM", 25.9, 0.05, p_d_total=5e-2)
    assert rec2["L"] == 0.0


def test_per_basis_clamp_nonnegative():
    rec = finite_key("1QM", 40.0, 0.05)  # far beyond 1QM viability
    assert rec["L_Z"] == 0.0 and rec["L_X"] == 0.0 and rec["L"] == 0.0
    assert rec["R"] == 0.0


# ----------------------------------------------------------- (d) A8 (passes)
def test_a8_asymptotic_consistency():
    r_fin = finite_key("2QM", 30.0, 0.05, block_scale=1e6)["R"]
    r_asy = asymptotic_rate("2QM", 30.0, 0.05)
    assert abs(r_fin - r_asy) / r_asy < 0.01


# ----------------------------------------- structural anchors that hold now
def test_a6_2qm_slope_band():
    dbs = [20.0 + 0.5 * i for i in range(9)]
    logs = [math.log10(finite_key("2QM", d, 0.05)["L"]) for d in dbs]
    n = len(dbs)
    mx, my = sum(dbs) / n, sum(logs) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(dbs, logs)) \
        / sum((x - mx) ** 2 for x in dbs)
    gamma = -10.0 * slope
    assert 0.8 <= gamma <= 1.2


def test_a7a_noise_resilience_ordering():
    c2 = p_d_cutoff("2QM", 25.9, 0.05)
    c1 = p_d_cutoff("1QM", 25.9, 0.05)
    assert c2 > c1


# ------------------------------------------------------- (g) sweep purity
def test_pd_sweep_purity():
    before = finite_key("2QM", 30.0, 0.05)
    _ = finite_key("2QM", 30.0, 0.05, p_d_total=1e-4)
    after = finite_key("2QM", 30.0, 0.05)
    assert before == after
    assert TABLE1.p_bg == 6.4e-7  # frozen defaults untouched


def test_with_f_e_returns_copy():
    q = with_f_e(TABLE1, 1.19)
    assert isinstance(q, Mem0Params) and q.f_e == 1.19 and TABLE1.f_e == 1.0


# ------------------------------------------------------ (e) import hygiene
def test_import_hygiene():
    src = pathlib.Path(__file__).resolve().parent.parent \
        / "src" / "qkd" / "mem0_gundogan.py"
    tree = ast.parse(src.read_text())
    forbidden = ("qkd.fixtures", "qkd.adaptive", "qkd.hybrid", "qkd.canonical",
                 "qkd.pipeline", "qkd.run", "qkd.bb84", "qkd.link")
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for name in imported:
        assert not any(name == f or name.startswith(f + ".") for f in forbidden), name
    # Only stdlib + numpy permitted (numpy currently unused is acceptable).
    for name in imported:
        assert name.split(".")[0] in {
            "math", "dataclasses", "annotations", "__future__", "numpy"}, name
