"""RECOH-1 instrument calibration: 25 obligations, numbered as in the packet.

All curve-based recovery positives are synthetic self-checks, not physical
models or evidence of rung-2 capability. Grids and tolerances are predeclared.
"""

import ast
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
import itertools
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from qkd import mem_state, recoh
from qkd.mem_state import (
    PLUS, MINUS, StoredQubit, density_matrix, dephase, choi_dephasing,
    is_cptp_dephasing, kappa_ideal, kappa_lindblad, kappa_gaussian, _g_ou,
)
from qkd.recoh import (
    RecoveryClass, coherence_l1, pure_target_fidelity, trace_distance,
    trace_distance_backflow, recovery_fraction, classify_recovery,
)

KAPPAS = (-1.0, -0.5, 0.0, 0.5, 1.0)
STATES = (PLUS, MINUS, StoredQubit(0, 0, 1), StoredQubit(0, 0, -1),
          StoredQubit(0, 0, 0), StoredQubit(0.3, -0.4, 0.6))
MODULE_PATHS = (Path(mem_state.__file__), Path(recoh.__file__))


def test_01_dephase_preserves_density_matrix_validity():
    for state, kappa in itertools.product(STATES, KAPPAS):
        rho = density_matrix(dephase(state, kappa))
        assert rho.shape == (2, 2) and np.iscomplexobj(rho)
        np.testing.assert_allclose(rho, rho.conj().T, rtol=0, atol=1e-12)
        assert np.trace(rho) == pytest.approx(1.0, rel=0, abs=1e-12)
        assert np.linalg.eigvalsh(rho).min() >= -1e-12
    np.testing.assert_array_equal(density_matrix(StoredQubit(0, 1, 0)),
                                  [[0.5, -0.5j], [0.5j, 0.5]])


def test_02_choi_cptp_normalization_and_physical_map_validation_split():
    for kappa in (-1.01, *KAPPAS, 1.01):
        choi = choi_dephasing(kappa)
        assert choi.shape == (4, 4)
        np.testing.assert_allclose(
            np.linalg.eigvalsh(choi), sorted((1 + kappa, 1 - kappa, 0, 0)),
            rtol=0, atol=1e-12,
        )
        assert np.trace(choi) == 2.0  # Unnormalized Choi; not a density matrix.
        partial_trace = np.trace(choi.reshape(2, 2, 2, 2), axis1=0, axis2=2)
        np.testing.assert_allclose(partial_trace, np.eye(2), rtol=0, atol=1e-12)
        assert is_cptp_dephasing(kappa) is (abs(kappa) <= 1)
    for kappa in (-1.01, 1.01):
        with pytest.raises(ValueError, match=r"\|kappa\| must be <= 1"):
            dephase(PLUS, kappa)
    for function in (choi_dephasing, is_cptp_dephasing, lambda k: dephase(PLUS, k)):
        for invalid in (float("nan"), float("inf"), -float("inf"), 1j):
            with pytest.raises(ValueError, match="kappa"):
                function(invalid)


def test_03_populations_and_rz_are_invariant():
    for state, kappa in itertools.product(STATES, KAPPAS):
        evolved = dephase(state, kappa)
        assert evolved.rz == state.rz
        np.testing.assert_array_equal(np.diag(density_matrix(evolved)),
                                      np.diag(density_matrix(state)))


def test_04_zero_D_phi_is_ideal_for_all_models():
    times = np.array([[0.0, 1e-8], [1.0, 50.0]])
    for values in (kappa_ideal(times), kappa_lindblad(times, 0),
                   kappa_gaussian(times, 0), kappa_gaussian(times, 0, 0.4)):
        np.testing.assert_array_equal(values, np.ones(times.shape))
    assert kappa_ideal(0) == kappa_lindblad(20, 0) == kappa_gaussian(20, 0, 0.4) == 1.0


def test_05_white_kernel_reuses_lindblad_exactly(monkeypatch):
    times = np.linspace(0, 10, 301)
    np.testing.assert_array_equal(kappa_gaussian(times, 0.7, None), kappa_lindblad(times, 0.7))
    assert kappa_gaussian(1.0, 0.7) == kappa_lindblad(1.0, 0.7)
    # Pin code-path identity as well as numeric equality.
    sentinel = object()
    calls = []
    def lindblad_spy(t, D_phi):
        calls.append((t, D_phi))
        return sentinel
    monkeypatch.setattr(mem_state, "kappa_lindblad", lindblad_spy)
    assert mem_state.kappa_gaussian(times, 0.7, None) is sentinel
    assert calls[0][0] is times and calls[0][1] == 0.7


def test_06_white_limit_fixes_D_phi_not_sigma_squared():
    D = 0.7
    times = np.linspace(0, 5 / D, 1001)
    tau_c = 1e-3 / D
    assert np.max(np.abs(kappa_gaussian(times, D, tau_c) - np.exp(-D * times))) < 1e-3
    sigma = 2.0
    taus = np.array([1e-1, 1e-2, 1e-3]) / sigma
    wrong_limit = np.array([kappa_gaussian(1 / sigma, sigma**2 * tau, tau) for tau in taus])
    assert np.all(np.diff(wrong_limit) > 0)
    assert 0.999 < wrong_limit[-1] <= 1.0


def test_07_short_time_gaussian_asymptote_uses_stable_g_ou(monkeypatch):
    # High-precision evaluation independently catches cancellation at very small x.
    with localcontext() as context:
        context.prec = 70
        for text in ("1e-12", "1e-8", "1e-4", "9.99e-4"):
            x = Decimal(text)
            exact = x - 1 + (-x).exp()
            assert _g_ou(float(x)) == pytest.approx(float(exact), rel=2e-11, abs=0)
    D, tau_c = 0.8, 0.4
    x = np.geomspace(1e-12, 1e-2, 200)
    calls = []
    original = mem_state._g_ou
    def g_spy(value):
        calls.append(np.array(value, copy=True))
        return original(value)
    monkeypatch.setattr(mem_state, "_g_ou", g_spy)
    actual = kappa_gaussian(tau_c * x, D, tau_c)
    assert len(calls) == 1
    np.testing.assert_allclose(calls[0], x, rtol=1e-15, atol=0)
    asymptote = np.exp(-D * tau_c * x**2 / 2)
    assert np.max(np.abs(actual / asymptote - 1)) < 1e-3


def test_08_ou_long_time_exponential_regime():
    D, tau_c = 0.5, 0.4
    t = 200 * tau_c
    assert abs(-math.log(kappa_gaussian(t, D, tau_c)) / (D * t) - 1) < 1e-2


def test_09_ou_monotonicity_and_series_switch_continuity():
    times = np.linspace(0, 10, 10_000)
    kappas = kappa_gaussian(times, 0.8, 0.3)
    assert kappas[0] == 1.0
    assert np.all(np.diff(kappas) <= 0)
    assert np.all((0 <= kappas) & (kappas <= 1))
    x = 1e-3
    series = x**2 / 2 - x**3 / 6 + x**4 / 24
    expm1_form = x + np.expm1(-x)
    assert abs(series - expm1_form) < 1e-12
    assert _g_ou(x) == expm1_form
    assert abs(_g_ou(np.nextafter(x, 0.0)) - _g_ou(x)) < 1e-12


def test_10_l1_coherence_matches_off_diagonal_and_absolute_kappa():
    assert coherence_l1(PLUS) == 1.0
    for kappa in KAPPAS:
        state = dephase(PLUS, kappa)
        assert coherence_l1(state) == abs(kappa)
        assert coherence_l1(state) == 2 * abs(density_matrix(state)[0, 1])
    assert coherence_l1(StoredQubit(0.3, -0.4, 0.6)) == 0.5


def test_11_pure_target_fidelity_convention_and_mixed_target_rejection():
    for kappa in KAPPAS:
        assert pure_target_fidelity(dephase(PLUS, kappa), PLUS) == (1 + kappa) / 2
    z_target = StoredQubit(0, 0, 1)
    for state in STATES:
        assert pure_target_fidelity(state, z_target) == density_matrix(state)[0, 0].real
    with pytest.raises(ValueError, match="target must be pure"):
        pure_target_fidelity(PLUS, StoredQubit(0.5, 0, 0))


def test_12_antipodal_pair_trace_distance_is_absolute_kappa():
    assert trace_distance(PLUS, MINUS) == 1.0
    for kappa in KAPPAS:
        assert trace_distance(dephase(PLUS, kappa), dephase(MINUS, kappa)) == abs(kappa)
    for state in STATES:
        assert trace_distance(state, state) == 0.0


def test_13_lindblad_and_ou_free_evolution_have_no_backflow():
    times = np.linspace(0, 10, 1001)
    for kappas in (kappa_lindblad(times, 0.7), kappa_gaussian(times, 0.7, 0.2)):
        distances = [trace_distance(dephase(PLUS, k), dephase(MINUS, k)) for k in kappas]
        assert trace_distance_backflow(distances, times) == 0.0


def test_14_backflow_synthetic_self_check_and_input_validation():
    """Synthetic self-check, not a physical model or a BLP state-pair maximization."""
    distances, times = [1, 0.6, 0.75, 0.4, 0.7], [0, 0.1, 2, 5, 100]
    assert trace_distance_backflow(distances, times) == pytest.approx(0.45, abs=1e-12)
    assert trace_distance_backflow([1, 0.7], [0, 100]) == 0.0  # Unsampled revival invisible.
    assert trace_distance_backflow([0.5], [0]) == 0.0
    cases = (([0, 1], [0], "lengths"), ([0, 1], [0, 0], "increasing"),
             ([0, 1], [1, 0], "increasing"), ([-0.01, 1], [0, 1], "D"),
             ([0, 1.01], [0, 1], "D"), ([0, np.nan], [0, 1], "D"),
             ([0, 1], [0, np.inf], "t"), ([], [], "non-empty"))
    for D, t, message in cases:
        with pytest.raises(ValueError, match=message):
            trace_distance_backflow(D, t)
    assert trace_distance_backflow([1 + 5e-13, -5e-13], [0, 1]) == 0.0


def test_15_every_recoh1_free_model_classifies_as_none():
    times = np.linspace(0, 10, 1001)
    for kappas in (kappa_ideal(times), kappa_lindblad(times, 0.7),
                   kappa_gaussian(times, 0.7), kappa_gaussian(times, 0.7, 0.2)):
        coherence = [coherence_l1(dephase(PLUS, k)) for k in kappas]
        assert classify_recovery(times, coherence) is RecoveryClass.NONE
        assert classify_recovery(times, coherence, backflow=0.0) is RecoveryClass.NONE


def test_16_classifier_synthetic_loss_then_revival_and_priority():
    """Synthetic category self-checks only; no physical control or revival model."""
    t = np.arange(4)
    free, protected, revival = [1, 0.8, 0.6, 0.4], [1, 0.9, 0.8, 0.7], [1, 0.5, 0.5, 0.8]
    assert classify_recovery(t, free, protected) is RecoveryClass.PROTECTION_ONLY
    assert classify_recovery(t, free, revival) is RecoveryClass.ACTIVE_REPHASING
    assert classify_recovery(t, revival, backflow=0.3) is RecoveryClass.ENVIRONMENTAL_BACKFLOW
    assert classify_recovery(t, revival, revival, backflow=0.3) is RecoveryClass.ENVIRONMENTAL_BACKFLOW
    assert classify_recovery(t, revival, backflow=0.0) is RecoveryClass.NONE
    assert classify_recovery(t, revival, backflow=1e-9) is RecoveryClass.NONE
    # Independent literal i<j<k search, including plateaus and a nonlocal dip.
    for values in itertools.product((0.0, 0.5, 1.0), repeat=5):
        expected = any(values[j] < values[i] - 1e-9 and values[k] > values[j] + 1e-9
                       for i, j, k in itertools.combinations(range(5), 3))
        result = classify_recovery(np.arange(5), values, backflow=0.5)
        assert result is (RecoveryClass.ENVIRONMENTAL_BACKFLOW if expected else RecoveryClass.NONE)
    for invalid_t, invalid_free, invalid_ctrl, message in (
        ([0, 0], [1, 0.5], None, "increasing"),
        ([0, 1], [1], None, "lengths"),
        ([0, 1], [1, 0.5], [1], "lengths"),
        ([0, 1], [1, np.nan], None, "C_free"),
        ([0, 1], [1, 0.5], [1, np.inf], "C_ctrl"),
    ):
        with pytest.raises(ValueError, match=message):
            classify_recovery(invalid_t, invalid_free, invalid_ctrl)
    for kwargs in ({"tol": -1}, {"tol": np.nan}, {"backflow": np.inf}):
        with pytest.raises(ValueError):
            classify_recovery([0, 1], [1, 0.5], **kwargs)


def test_17_endpoint_improvement_is_protection_and_recovery_fraction_is_unclamped():
    assert classify_recovery([0, 1, 2], [1, 0.6, 0.2], [0.5, 0.5, 0.5]) is RecoveryClass.PROTECTION_ONLY
    assert classify_recovery([0, 1, 2], [1, 0.6, 0.2], [0.3, 0.4, 0.5]) is RecoveryClass.PROTECTION_ONLY
    assert classify_recovery([0, 1, 2], [1, 0.6, 0.2], [1, 0.8, 0.1]) is RecoveryClass.NONE
    assert recovery_fraction(1, 0.5, 0.75) == 0.5
    assert recovery_fraction(1, 0.75, 0.25) == -2.0
    assert recovery_fraction(0.75, 0.5, 1) == 2.0
    for free in (1.0, 1.0 - 5e-13, 1.0 + 5e-13):
        with pytest.raises(ValueError, match="recovery fraction undefined: no recoverable coherence loss occurred"):
            recovery_fraction(1, free, 1)
    for args in ((np.nan, 0, 0.5), (1, np.inf, 0.5), (1, 0, np.nan)):
        with pytest.raises(ValueError):
            recovery_fraction(*args)


def test_18_import_hygiene_and_provisional_configuration_notice():
    forbidden = ("qkd.effects", "qkd.link", "qkd.adaptive", "qkd.hybrid", "qkd.fixtures",
                 "qkd.mission", "qkd.schema", "qkd.mem0_gundogan", "numpy.random", "random")
    notice = ("Configuration names in this module are PROVISIONAL pending the memory SPEC\n"
              "amendment (RECOH-0 v0.2 §4); reconciliation is a RECOH-2 obligation.")
    for path in MODULE_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert notice in ast.get_docstring(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0
                imports = [node.module]
            else:
                continue
            for name in imports:
                assert not any(name == item or name.startswith(item + ".") for item in forbidden)
                assert (name.split(".")[0] in sys.stdlib_module_names or name == "numpy"
                        or (path.name == "recoh.py" and name == "qkd.mem_state"))
    result = subprocess.run(
        [sys.executable, "-c", "import qkd.mem_state, qkd.recoh; import sys; "
         "assert 'qkd.effects' not in sys.modules; assert 'qkd.link' not in sys.modules"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_19_modules_do_not_reference_rng_apis():
    for path in MODULE_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in {"random", "default_rng", "RandomState"}
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"random", "default_rng", "RandomState", "SeedSequence"}
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                assert all(alias.name not in {"random", "default_rng", "RandomState"} for alias in node.names)


def test_20_default_production_emission_and_schema_extensions_unchanged(tmp_path, monkeypatch, capsys):
    from qkd import run
    from qkd.schema import DECLARED_SCHEMA_EXTENSIONS

    # Read from main @215a876 before edits: two containing sections, one key each.
    assert len(DECLARED_SCHEMA_EXTENSIONS) == 2
    assert DECLARED_SCHEMA_EXTENSIONS == {
        "profile": {"link_receiver"}, "run_metadata": {"link_provenance"},
    }
    monkeypatch.setattr(run, "OUTPUTS_DIR", str(tmp_path))
    run.main()
    baseline = (tmp_path / "results.json").read_bytes()
    assert capsys.readouterr().out.strip() == "Dashboard Updated: Min loss 27.7 dB | Fidelity 0.990"
    times = np.linspace(0, 2, 21)
    kappas = kappa_gaussian(times, 0.7, 0.2)
    values = [coherence_l1(dephase(PLUS, kappa)) for kappa in kappas]
    assert classify_recovery(times, values) is RecoveryClass.NONE
    run.main()
    assert (tmp_path / "results.json").read_bytes() == baseline
    assert capsys.readouterr().out.strip() == "Dashboard Updated: Min loss 27.7 dB | Fidelity 0.990"


def test_21_negative_or_nonfinite_D_phi_is_rejected():
    for D in (-0.1, float("nan"), float("inf"), 1j):
        for function in (lambda: kappa_lindblad([0, 1], D),
                         lambda: kappa_gaussian([0, 1], D),
                         lambda: kappa_gaussian([0, 1], D, 0.2)):
            with pytest.raises(ValueError, match="D_phi"):
                function()


def test_22_nonpositive_or_nonfinite_tau_c_is_rejected_even_at_zero_rate():
    for tau in (0, -1, float("nan"), float("inf"), 1j):
        for D in (0, 1):
            with pytest.raises(ValueError, match="tau_c"):
                kappa_gaussian([0, 1], D, tau)


def test_23_negative_or_nonfinite_time_is_rejected():
    for times in (-1, [0, -1], [0, np.nan], [0, np.inf], [0, 1j]):
        for function in (lambda: kappa_ideal(times), lambda: kappa_lindblad(times, 0.7),
                         lambda: kappa_gaussian(times, 0.7),
                         lambda: kappa_gaussian(times, 0.7, 0.2)):
            with pytest.raises(ValueError, match="t"):
                function()


def test_24_bloch_ball_and_finite_components_are_validated_without_renormalizing():
    for vector in ((1.01, 0, 0), (0, 1.01, 0), (0, 0, -1.01), (0.8, 0.8, 0)):
        with pytest.raises(ValueError, match=r"\|r\|"):
            StoredQubit(*vector)
    for index, name in enumerate(("rx", "ry", "rz")):
        for value in (np.nan, np.inf, -np.inf):
            vector = [0.0, 0.0, 0.0]
            vector[index] = value
            with pytest.raises(ValueError, match=name):
                StoredQubit(*vector)
    accepted = StoredQubit(1 + 5e-13, 0, 0)
    assert accepted.rx == 1 + 5e-13
    with pytest.raises(FrozenInstanceError):
        accepted.rx = 0.0


def test_25_dephasing_composes_by_multiplying_coherence_factors():
    grid = (-0.9, -0.3, 0.0, 0.4, 1.0)
    for state, first, second in itertools.product(STATES, grid, grid):
        sequential = dephase(dephase(state, first), second)
        composed = dephase(state, first * second)
        np.testing.assert_allclose(
            (sequential.rx, sequential.ry, sequential.rz),
            (composed.rx, composed.ry, composed.rz), rtol=0, atol=1e-12,
        )
