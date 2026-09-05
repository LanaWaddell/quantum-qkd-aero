"""RECOH-2 active-rephasing calibration: proof obligations, numbered as in the
rev 1.2 packet. All curve-based recovery positives here are on the declared
single-qubit reference model; only the certified reference claim is rung 2.
"""

import ast
from decimal import Decimal, localcontext
import math
from pathlib import Path
import sys

import numpy as np
import pytest

from qkd import mem_state, recoh
from qkd.mem_state import (
    PLUS, MINUS, StoredQubit, EchoModel, pi_pulse_x, purity, echo_h, echo_F,
    var_free, var_ctrl, echo_peak_time, stored_state_at, evolve, dephase,
    _g_ou,
)
from qkd.recoh import (
    RecoveryStatus, GuardStatus, GuardResult, RecoveryReport, RecoveryClass,
    coherence_l1, pure_target_fidelity, trace_distance_backflow,
    recovery_fraction, classify_recovery, echo_grid, purity_guard,
    recovery_report,
)

MODULE_PATHS = (Path(mem_state.__file__), Path(recoh.__file__))
RATIFIED_NOTICE = (
    "Configuration names in this module (`dephasing_model`, `noise_kernel`, `D_phi`,\n"
    "`tau_c`) follow SPEC-memory-lifetime-adr0003 (ratified 2026-09-03, `81c97ed`);\n"
    "`kappa_ideal` corresponds to `identity_state_evolution`."
)
NON_EQUATORIAL = StoredQubit(0.6, 0.0, 0.8)
REF_MODEL = EchoModel(PLUS, D_phi=1.0, tau_c=2.0, tau=3.0)


# --- State map and pulse ----------------------------------------------------


def test_01_pi_pulse_preserves_coherence_purity_trace_and_is_an_involution():
    for state in (PLUS, MINUS, NON_EQUATORIAL, StoredQubit(0, 0, 1), StoredQubit(0.3, -0.4, 0.6)):
        pulsed = pi_pulse_x(state)
        assert coherence_l1(pulsed) == pytest.approx(coherence_l1(state), abs=0, rel=0)
        assert purity(pulsed) == pytest.approx(purity(state), abs=0, rel=0)
        rho = mem_state.density_matrix(pulsed)
        assert np.trace(rho).real == pytest.approx(1.0, abs=1e-12)
        involuted = pi_pulse_x(pulsed)
        assert (involuted.rx, involuted.ry, involuted.rz) == (state.rx, state.ry, state.rz)


def test_02_state_map_continuous_through_tau_with_sign_flips():
    model = EchoModel(StoredQubit(0.3, -0.4, 0.6), D_phi=1.0, tau_c=2.0, tau=3.0)
    before = stored_state_at(model, model.tau - 1e-9, controlled=True)
    at_tau = stored_state_at(model, model.tau, controlled=True)
    after = stored_state_at(model, model.tau + 1e-9, controlled=True)
    assert coherence_l1(before) == pytest.approx(coherence_l1(at_tau), abs=1e-6)
    assert coherence_l1(at_tau) == pytest.approx(coherence_l1(after), abs=1e-6)
    assert purity(before) == pytest.approx(purity(at_tau), abs=1e-9)
    assert purity(at_tau) == pytest.approx(purity(after), abs=1e-9)
    just_before_free = stored_state_at(model, model.tau, controlled=False)
    post_pulse = pi_pulse_x(just_before_free)
    assert at_tau.ry == pytest.approx(post_pulse.ry, abs=1e-12, rel=1e-12)
    assert at_tau.rz == pytest.approx(post_pulse.rz, abs=1e-12, rel=1e-12)
    assert just_before_free.ry < 0 < at_tau.ry
    assert at_tau.rz == -just_before_free.rz
    assert at_tau.rz < 0 < just_before_free.rz


def test_03_non_equatorial_state_flips_rz_and_witnesses_equal_w_times_c0():
    model = EchoModel(NON_EQUATORIAL, D_phi=0.9, tau_c=1.5, tau=2.0)
    C0 = coherence_l1(NON_EQUATORIAL)
    assert C0 == pytest.approx(0.6, abs=1e-12)
    for t in (0.5, model.tau, model.tau + 1.0):
        free_state = stored_state_at(model, t, controlled=False)
        ctrl_state = stored_state_at(model, t, controlled=True)
        W_free = math.exp(-var_free(model, t) / 2.0)
        assert coherence_l1(free_state) == pytest.approx(W_free * C0, rel=1e-12)
        if t >= model.tau:
            W_ctrl = math.exp(-var_ctrl(model, t) / 2.0)
            assert coherence_l1(ctrl_state) == pytest.approx(W_ctrl * C0, rel=1e-12)
            assert ctrl_state.rz == pytest.approx(-NON_EQUATORIAL.rz, abs=1e-12)


def test_04_evolve_matches_stored_state_at_pointwise():
    model = REF_MODEL
    grid = np.linspace(0.0, 2 * model.tau, 37)
    for controlled in (False, True):
        batch = evolve(model, grid, controlled)
        pointwise = [stored_state_at(model, float(t), controlled) for t in grid]
        for a, b in zip(batch, pointwise):
            assert (a.rx, a.ry, a.rz) == (b.rx, b.ry, b.rz)


def test_05_history_unaware_restart_gives_smaller_c_ctrl_at_2tau():
    model = REF_MODEL
    two_tau = 2 * model.tau
    correct = stored_state_at(model, two_tau, controlled=True)
    # Wrong (forbidden) approach: restart independent dephasing from r(tau).
    at_tau = stored_state_at(model, model.tau, controlled=True)
    kappa_restart = mem_state.kappa_gaussian(two_tau - model.tau, model.D_phi, model.tau_c)
    restarted = StoredQubit(kappa_restart * at_tau.rx, kappa_restart * at_tau.ry, at_tau.rz)
    assert coherence_l1(correct) > coherence_l1(restarted)


# --- Evaluator ---------------------------------------------------------------


def test_06_var_free_matches_g_ou_scaling():
    model = REF_MODEL
    times = np.linspace(0, 10, 101)
    expected = 2 * model.D_phi * model.tau_c * _g_ou(times / model.tau_c)
    got = var_free(model, times)
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=0)


def test_07_hahn_law_at_2tau():
    model = REF_MODEL
    expected = 2 * model.D_phi * model.tau_c * echo_h(2 * model.tau / model.tau_c)
    got = var_ctrl(model, 2 * model.tau)
    assert got == pytest.approx(expected, rel=1e-12)


def _decimal_h(x):
    return x - 3 + 4 * (-x / 2).exp() - (-x).exp()


def test_08a_echo_h_series_matches_decimal():
    with localcontext() as ctx:
        ctx.prec = 60
        for text in ("1e-4", "1e-3", "9e-3", "1e-2", "0.05", "0.49"):
            x = Decimal(text)
            exact = float(_decimal_h(x))
            got = echo_h(float(text))
            assert got > 0
            assert abs(got - exact) / abs(exact) < 1e-14


def test_08b_echo_h_direct_branch_matches_decimal():
    with localcontext() as ctx:
        ctx.prec = 60
        for xv in (0.5, 0.51, 1, 2, 5):
            exact = float(_decimal_h(Decimal(xv)))
            got = echo_h(float(xv))
            assert abs(got - exact) / abs(exact) < 1e-13


def test_08c_series_and_direct_branches_agree_near_the_switch():
    at_switch_direct = echo_h(0.5)
    just_below_series = echo_h(0.4999)
    assert abs(at_switch_direct - just_below_series) / abs(at_switch_direct) < 1e-3
    # Forcing both formulas directly at the same x confirms they agree to spec tolerance.
    x = 0.4999
    direct_form = x - 3 + 4 * math.exp(-x / 2) - math.exp(-x)
    assert abs(direct_form - just_below_series) / abs(direct_form) < 1e-13
    x2 = 0.5
    direct_form2 = x2 - 3 + 4 * math.exp(-x2 / 2) - math.exp(-x2)
    assert abs(direct_form2 - at_switch_direct) / abs(direct_form2) < 1e-13


def test_08d_echo_h_edge_cases_and_no_runtime_error():
    assert echo_h(0.0) == 0.0
    assert echo_h(1e-120) == 0.0
    subnormal = 5e-324
    result = echo_h(subnormal)
    assert math.isfinite(result) and result >= 0.0
    assert echo_h(1e-4) > 0
    for x in (0.0, 1e-120, subnormal, 1e-4):
        echo_h(x)  # must return within a nominal timeout; no RuntimeError raised.
    with pytest.raises(ValueError, match="x"):
        echo_h(-1.0)


def test_09a_echo_F_matches_70digit_decimal():
    sqrt3 = math.sqrt(3.0)
    cases = [
        (1e-3, (2 - sqrt3) * 1e-3), (1e-2, (2 - sqrt3) * 1e-2), (1e-8, 1e-8),
        (1e-3, 0.0), (0.05, 0.0499), (0.25, 0.25), (1.5, 1.0), (3.0, 0.2),
    ]
    with localcontext() as ctx:
        ctx.prec = 80
        for a, b in cases:
            aD, bD = Decimal(a), Decimal(b)
            delta = (-min(aD, bD)).exp() * (1 - (-abs(aD - bD)).exp())
            exact = float((_decimal_h(2 * aD) + _decimal_h(2 * bD) + delta**2) / 2)
            got = echo_F(a, b)
            assert got > 0
            assert abs(got - exact) / abs(exact) < 1e-13


def test_09b_F_of_equal_arguments_equals_h_of_double_bitwise():
    for a in (0.0, 0.3, 1.5, 5.0, 30000.0):
        assert echo_F(a, a) == echo_h(2 * a)


def test_09c_F_at_origin_is_exact_zero():
    assert echo_F(0.0, 0.0) == 0.0


def test_09d_var_ctrl_near_peak_matches_decimal():
    ratio = 0.01
    model = EchoModel(PLUS, D_phi=1.0, tau_c=1.0 / ratio, tau=1.0)
    t_peak = echo_peak_time(model)
    a = Decimal(model.tau) / Decimal(model.tau_c)
    b = (Decimal(t_peak) - Decimal(model.tau)) / Decimal(model.tau_c)
    with localcontext() as ctx:
        ctx.prec = 70
        delta = (-min(a, b)).exp() * (1 - (-abs(a - b)).exp())
        F_exact = (_decimal_h(2 * a) + _decimal_h(2 * b) + delta**2) / 2
        exact_var = float(2 * Decimal(model.D_phi) * Decimal(model.tau_c) * F_exact)
    got = var_ctrl(model, t_peak)
    assert got == pytest.approx(exact_var, rel=1e-12)


def test_10_exact_t_peak_matches_grid_argmax():
    for ratio in (0.1, 1.0, 5.0, 20.0):
        tau_c = 1.0
        tau = ratio * tau_c
        model = EchoModel(PLUS, D_phi=1.0, tau_c=tau_c, tau=tau)
        t_peak = echo_peak_time(model)
        spacing = tau_c * 1e-4
        grid = np.arange(tau, tau + 4 * tau_c, spacing)
        var_grid = np.asarray(var_ctrl(model, grid), dtype=float)
        argmax_t = grid[np.argmin(var_grid)]
        assert abs(argmax_t - t_peak) <= spacing


def test_11_small_ratio_series_and_monotone_convergence():
    tau_c = 1.0
    ratio = 0.01
    tau = ratio * tau_c
    model = EchoModel(PLUS, D_phi=1.0, tau_c=tau_c, tau=tau)
    t_peak = echo_peak_time(model)
    approx_series = 2 * tau - tau**2 / tau_c
    assert abs(t_peak - approx_series) < 1e-3 * 2 * tau
    ratios = np.array([1e-1, 1e-2, 1e-3])
    values = []
    for r in ratios:
        m = EchoModel(PLUS, D_phi=1.0, tau_c=1.0, tau=r)
        values.append(echo_peak_time(m) / (2 * r))
    assert np.all(np.diff(values) > 0)  # monotone increase toward 1 as ratio shrinks.
    assert values[-1] > 1.0 - 1e-3


def test_12_large_ratio_limit():
    tau_c = 1.0
    tau = 20.0 * tau_c
    model = EchoModel(PLUS, D_phi=1.0, tau_c=tau_c, tau=tau)
    t_peak = echo_peak_time(model)
    limit = tau + tau_c * math.log(2.0)
    assert abs(t_peak - limit) / limit < 0.01


def test_13_right_derivative_at_tau_is_negative_and_c_ctrl_rises_first_step():
    model = REF_MODEL
    h = 1e-6
    var_before_tau = var_ctrl(model, model.tau)
    var_after_tau = var_ctrl(model, model.tau + h)
    assert var_after_tau < var_before_tau
    grid = np.array([model.tau, model.tau + model.tau_c * 1e-3])
    c_ctrl = [coherence_l1(stored_state_at(model, t, controlled=True)) for t in grid]
    assert c_ctrl[1] > c_ctrl[0]


def test_14_reference_numbers_to_7_significant_figures():
    model = REF_MODEL
    C0 = coherence_l1(model.r0)
    t_peak = echo_peak_time(model)
    two_tau = 2 * model.tau
    C_free_peak = coherence_l1(stored_state_at(model, t_peak, controlled=False))
    C_ctrl_peak = coherence_l1(stored_state_at(model, t_peak, controlled=True))
    R_peak = recovery_fraction(C0, C_free_peak, C_ctrl_peak)
    C_free_2tau = coherence_l1(stored_state_at(model, two_tau, controlled=False))
    C_ctrl_2tau = coherence_l1(stored_state_at(model, two_tau, controlled=True))
    R_2tau = recovery_fraction(C0, C_free_2tau, C_ctrl_2tau)

    # Packet reference numbers are quoted to 7 digits after the decimal point.
    assert t_peak == pytest.approx(4.1497066, abs=1e-7)
    assert C_free_peak == pytest.approx(0.0906403, abs=1e-7)
    assert C_ctrl_peak == pytest.approx(0.3526683, abs=1e-7)
    assert R_peak == pytest.approx(0.2881456, abs=1e-7)
    assert C_free_2tau == pytest.approx(0.0165797, abs=1e-7)
    assert C_ctrl_2tau == pytest.approx(0.1853578, abs=1e-7)
    assert R_2tau == pytest.approx(0.1716236, abs=1e-7)


# --- Guard and loophole -------------------------------------------------------


def test_15_purity_identity_on_both_trajectories_at_every_grid_time():
    for r0 in (PLUS, NON_EQUATORIAL):
        model = EchoModel(r0, D_phi=1.0, tau_c=2.0, tau=3.0)
        grid = echo_grid(model, 50)
        free_states = evolve(model, grid, controlled=False)
        ctrl_states = evolve(model, grid, controlled=True)
        guard = purity_guard(free_states, ctrl_states, r0.rz)
        assert guard.status is GuardStatus.PASSED
        assert guard.max_abs_dev <= 1e-12


def test_16_purity_non_increase_with_expected_equalities():
    # Purity depends on |kappa|; sweep |kappa| decreasing from 1 to 0 (kappa >= 0
    # suffices since dephase only ever scales the transverse components).
    abs_kappas = np.linspace(1.0, 0.0, 11)
    eigenstate = StoredQubit(0, 0, 1)
    diagonal_mixed = StoredQubit(0, 0, 0.4)
    maximally_mixed = StoredQubit(0, 0, 0)
    plus = PLUS
    for state, expect_equal in (
        (eigenstate, True), (diagonal_mixed, True), (maximally_mixed, True), (plus, False),
    ):
        purities = [purity(dephase(state, k)) for k in abs_kappas]
        diffs = np.diff(purities)
        assert np.all(diffs <= 1e-15)  # non-increasing as |kappa| decreases from 1 to 0.
        if expect_equal:
            assert max(purities) == pytest.approx(min(purities), abs=1e-12)
        else:
            assert max(purities) > min(purities) + 1e-9


def test_17_z_precession_loophole_distinguishes_F_from_C_l1():
    # Synthetic self-check: an F-based curve can cycle while C_l1/purity stay
    # constant (pure Z precession carries no coherence-witness information).
    t = np.linspace(0, 10, 11)
    f_curve = 0.5 + 0.5 * np.cos(t)  # revives: dips then rises.
    c_l1_curve = np.full_like(t, 0.7)  # constant: no revival visible to C_l1.
    assert classify_recovery(t, f_curve) is not RecoveryClass.NONE or \
        classify_recovery(t, f_curve, backflow=0.5) is RecoveryClass.ENVIRONMENTAL_BACKFLOW
    assert classify_recovery(t, c_l1_curve, backflow=0.5) is RecoveryClass.NONE


def test_18_guard_none_handling_and_corruption_detection():
    assert purity_guard(None, None, 0.0).status is GuardStatus.NOT_EVALUATED
    with pytest.raises(ValueError):
        purity_guard([PLUS], None, 0.0)
    with pytest.raises(ValueError):
        purity_guard(None, [PLUS], 0.0)

    model = EchoModel(NON_EQUATORIAL, D_phi=1.0, tau_c=2.0, tau=3.0)
    grid = echo_grid(model, 20)
    free_states = list(evolve(model, grid, controlled=False))
    ctrl_states = list(evolve(model, grid, controlled=True))

    corrupted = list(ctrl_states)
    interior = len(corrupted) // 2
    s = corrupted[interior]
    corrupted[interior] = StoredQubit(s.rx, s.ry, s.rz * 0.9)
    guard_bad = purity_guard(free_states, corrupted, NON_EQUATORIAL.rz)
    assert guard_bad.status is GuardStatus.FAILED

    transverse_only = list(ctrl_states)
    s2 = transverse_only[interior]
    scale = 0.9999999999
    transverse_only[interior] = StoredQubit(s2.rx * scale, s2.ry * scale, s2.rz)
    guard_ok = purity_guard(free_states, transverse_only, NON_EQUATORIAL.rz)
    assert guard_ok.status is not GuardStatus.FAILED


# --- Rung-2 test and controls -------------------------------------------------


def test_19_reference_report_earns_active_rephasing():
    report = recovery_report(REF_MODEL, 200)
    assert report.recovery_status is RecoveryStatus.AVAILABLE
    assert report.recovery_class is RecoveryClass.ACTIVE_REPHASING
    assert report.valid is True
    assert report.R_peak > report.R_2tau > 0
    assert report.backflow_free == 0.0

    def sig6(x):
        return float(f"{x:.6g}")

    assert sig6(report.R_peak) == pytest.approx(0.288146, rel=1e-5)
    assert sig6(report.R_2tau) == pytest.approx(0.171624, rel=1e-5)

    ctrl_2tau = stored_state_at(REF_MODEL, 2 * REF_MODEL.tau, controlled=True)
    identity_fidelity = (1.0 + coherence_l1(ctrl_2tau)) / 2.0
    assert report.fidelity["2tau"] == pytest.approx(identity_fidelity, abs=1e-12)
    assert "t_peak" in report.fidelity


def test_20_lindblad_control_reports_no_peak_with_matching_trajectories():
    model = EchoModel(PLUS, D_phi=0.7, tau_c=None, tau=3.0)
    report = recovery_report(model, 50)
    assert report.recovery_status is RecoveryStatus.NO_PEAK
    assert report.R_2tau == 0.0
    assert report.recovery_class is RecoveryClass.NONE
    grid = echo_grid(model, 50)
    free_states = evolve(model, grid, controlled=False)
    ctrl_states = evolve(model, grid, controlled=True)
    for f, c in zip(free_states, ctrl_states):
        assert coherence_l1(f) == pytest.approx(coherence_l1(c), abs=1e-15)


def test_20b_weak_white_noise_reports_no_peak_before_loss_resolution():
    model = EchoModel(PLUS, D_phi=1e-14, tau_c=None, tau=3.0)
    report = recovery_report(model, 50)
    assert report.recovery_status is RecoveryStatus.NO_PEAK


def test_21_ou_to_lindblad_convergence():
    D_phi, tau, tau_c = 1.0, 3.0, 1e-4
    model = EchoModel(PLUS, D_phi=D_phi, tau_c=tau_c, tau=tau)
    t_peak = echo_peak_time(model)
    base_grid = np.linspace(0.0, 6.0, 200_000)
    grid = np.unique(np.concatenate([base_grid, [tau, t_peak]]))
    free_states = evolve(model, grid, controlled=False)
    ctrl_states = evolve(model, grid, controlled=True)
    C_free = np.array([coherence_l1(s) for s in free_states])
    C_ctrl = np.array([coherence_l1(s) for s in ctrl_states])
    exp_curve = np.exp(-grid)
    assert np.max(np.abs(C_free - exp_curve)) < 1.1e-4
    assert np.max(np.abs(C_ctrl - exp_curve)) < 1.1e-4
    assert np.max(np.abs(C_ctrl - C_free)) < 1.1e-5
    idx_2tau = int(np.argmin(np.abs(grid - 2 * tau)))
    assert abs(C_ctrl[idx_2tau] - C_free[idx_2tau]) < 6e-7
    report = recovery_report(model, 50)
    assert report.R_peak is not None and report.R_peak < 1e-5


def test_21b_documentation_case_small_tau():
    D_phi, tau, tau_c = 1.0, 0.1, 1e-4
    model = EchoModel(PLUS, D_phi=D_phi, tau_c=tau_c, tau=tau)
    two_tau = 2 * tau
    C_free = coherence_l1(stored_state_at(model, two_tau, controlled=False))
    C_ctrl = coherence_l1(stored_state_at(model, two_tau, controlled=True))
    diff = abs(C_ctrl - C_free)
    assert abs(diff - 1.64e-4) / 1.64e-4 < 0.05


def test_22_zero_D_phi_reports_no_loss_without_exceptions():
    model = EchoModel(PLUS, D_phi=0.0, tau_c=2.0, tau=3.0)
    assert echo_peak_time(model) is None
    report = recovery_report(model, 50)
    assert report.recovery_status is RecoveryStatus.NO_LOSS
    assert report.reason == "zero noise intensity"


def test_23a_diagonal_state_reports_no_loss_with_c_l1_zero():
    model = EchoModel(StoredQubit(0, 0, 1), D_phi=1.0, tau_c=2.0, tau=3.0)
    report = recovery_report(model, 50)
    assert report.recovery_status is RecoveryStatus.NO_LOSS
    assert report.reason == "zero initial transverse coherence"
    grid = echo_grid(model, 20)
    states = evolve(model, grid, controlled=True)
    assert all(coherence_l1(s) == 0.0 for s in states)
    guard = purity_guard(evolve(model, grid, controlled=False), states, 1.0)
    assert guard.status is GuardStatus.PASSED


def test_23b_white_kernel_and_diagonal_state_reports_no_loss():
    model = EchoModel(StoredQubit(0, 0, 1), D_phi=1.0, tau_c=None, tau=3.0)
    report = recovery_report(model, 50)
    assert report.recovery_status is RecoveryStatus.NO_LOSS


def test_23c_unresolved_loss_names_the_read_time_without_valueerror():
    model = EchoModel(PLUS, D_phi=1e-14, tau_c=2.0, tau=3.0)
    report = recovery_report(model, 50)  # must not raise ValueError internally
    assert report.recovery_status is RecoveryStatus.UNRESOLVED_LOSS
    assert "t_peak" in report.reason or "2tau" in report.reason
    assert report.R_peak is None and report.R_2tau is None


def test_23d_recovery_fraction_raises_on_zero_loss():
    with pytest.raises(ValueError, match="recovery fraction undefined"):
        recovery_fraction(1.0, 1.0, 0.5)


def test_23e_echo_grid_properties():
    model = REF_MODEL
    grid = echo_grid(model, 16)
    assert grid[0] == 0.0
    assert grid[-1] == pytest.approx(2 * model.tau)
    assert np.all(np.diff(grid) > 0)
    assert len(np.unique(grid)) == len(grid)
    assert model.tau in grid
    t_peak = echo_peak_time(model)
    assert t_peak in grid
    with pytest.raises(ValueError, match="n"):
        echo_grid(model, 7)


def test_23f_evolve_rejects_bad_grids():
    model = REF_MODEL
    for bad in ([1.0, 0.0], [0.0, 0.0], [0.0, np.nan], [0.0, np.inf]):
        with pytest.raises(ValueError):
            evolve(model, bad, controlled=False)


# --- Hygiene -------------------------------------------------------------


def test_24_docstrings_carry_ratified_notice_and_no_provisional():
    for path in MODULE_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstring = ast.get_docstring(tree)
        assert RATIFIED_NOTICE in docstring
        assert "PROVISIONAL" not in docstring


def test_25_import_hygiene_and_no_rng():
    forbidden = ("qkd.effects", "qkd.link", "qkd.adaptive", "qkd.hybrid", "qkd.fixtures",
                 "qkd.mission", "qkd.schema", "qkd.mem0_gundogan", "numpy.random", "random")
    rng_names = {"random", "default_rng", "RandomState", "SeedSequence"}
    for path in MODULE_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0
                imports = [node.module]
            else:
                imports = []
            for name in imports:
                assert not any(name == item or name.startswith(item + ".") for item in forbidden)
                assert (name.split(".")[0] in sys.stdlib_module_names or name == "numpy"
                        or (path.name == "recoh.py" and name == "qkd.mem_state"))
            if isinstance(node, ast.Name):
                assert node.id not in rng_names
            if isinstance(node, ast.Attribute):
                assert node.attr not in rng_names


def test_26_hygiene_scan_no_herald_or_success_probability_names():
    forbidden_tokens = ("herald", "success_prob", "acceptance_rule", "heralded")
    for path in MODULE_PATHS:
        source = path.read_text(encoding="utf-8").lower()
        for token in forbidden_tokens:
            assert token not in source
