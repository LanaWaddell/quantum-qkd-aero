import math

import pytest

pytest.importorskip("qiskit")

from qkd.teleportation import teleportation_fidelity


ATOL = 1e-9
CASES = (0.0, 0.2, 1.0 / 3.0, 0.5, 1.0 / math.sqrt(2.0), 0.9, 1.0)


@pytest.mark.parametrize("werner_p", CASES)
def test_qiskit_resource_singlet_fraction_guards_lambda_mapping(werner_p):
    result = teleportation_fidelity(werner_p, method="qiskit")

    assert math.isclose(result.singlet_fraction, (1.0 + 3.0 * werner_p) / 4.0, abs_tol=ATOL)


@pytest.mark.parametrize("werner_p", CASES)
def test_qiskit_average_fidelity_matches_analytic_formula(werner_p):
    result = teleportation_fidelity(werner_p, method="qiskit")

    assert math.isclose(result.fidelity, (1.0 + werner_p) / 2.0, abs_tol=ATOL)


@pytest.mark.parametrize("werner_p", CASES)
def test_qiskit_method_matches_analytic_method_end_to_end(werner_p):
    analytic = teleportation_fidelity(werner_p, method="analytic")
    qiskit = teleportation_fidelity(werner_p, method="qiskit")

    assert math.isclose(qiskit.fidelity, analytic.fidelity, abs_tol=ATOL)
    assert math.isclose(qiskit.singlet_fraction, analytic.singlet_fraction, abs_tol=ATOL)
    assert qiskit.beats_classical is analytic.beats_classical
    assert math.isclose(qiskit.margin, analytic.margin, abs_tol=ATOL)
    assert qiskit.method == "qiskit"
