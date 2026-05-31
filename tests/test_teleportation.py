import pytest

from qkd.teleportation import (
    TeleportationMission,
    TeleportationResult,
    build_teleportation_results,
    teleportation_fidelity,
)


def test_teleportation_mission_current_output_lengths():
    frames, fidelities, resources = TeleportationMission().run_teleportation()

    assert len(frames) == 1000
    assert len(fidelities) == 1000
    assert len(resources) == 1000


def test_build_teleportation_results_current_schema():
    frames = [0, 1]
    fidelities = [0.8, 0.9]
    resources = [14.99, 14.98]

    results = build_teleportation_results(frames, fidelities, resources, "outputs/example.png")

    assert results["teleportation"]["frames"] == 2
    assert results["teleportation"]["average_fidelity"] == 0.85
    assert results["summary"]["headline_key_yield"] == "14.98 Kb"
    assert results["summary"]["headline_fidelity"] == "0.850"


@pytest.mark.parametrize("method", ["analytic", "numeric"])
def test_teleportation_fidelity_returns_result_object(method):
    result = teleportation_fidelity(0.9, method=method)

    assert isinstance(result, TeleportationResult)
    assert result.method == method


@pytest.mark.parametrize("method", ["analytic", "numeric"])
def test_teleportation_fidelity_constants(method):
    perfect = teleportation_fidelity(1.0, method=method)
    threshold = teleportation_fidelity(1 / 3, method=method)
    mixed = teleportation_fidelity(0.0, method=method)

    assert perfect.fidelity == pytest.approx(1.0, abs=1e-12)
    assert perfect.singlet_fraction == pytest.approx(1.0, abs=1e-12)
    assert perfect.beats_classical is True

    assert threshold.fidelity == pytest.approx(2 / 3, abs=1e-12)
    assert threshold.singlet_fraction == pytest.approx(0.5, abs=1e-12)
    assert threshold.classical_bound == pytest.approx(2 / 3, abs=1e-12)
    assert threshold.beats_classical is False
    assert threshold.margin == pytest.approx(0.0, abs=1e-12)

    assert mixed.fidelity == pytest.approx(0.5, abs=1e-12)
    assert mixed.singlet_fraction == pytest.approx(0.25, abs=1e-12)
    assert mixed.beats_classical is False


def test_teleportation_numeric_matches_analytic():
    for werner_p in [0.0, 1 / 3, 0.5, 0.9, 1.0]:
        analytic = teleportation_fidelity(werner_p, method="analytic")
        numeric = teleportation_fidelity(werner_p, method="numeric")

        assert numeric.fidelity == pytest.approx(analytic.fidelity, abs=1e-12)
        assert numeric.singlet_fraction == pytest.approx(analytic.singlet_fraction, abs=1e-12)
        assert numeric.beats_classical is analytic.beats_classical
        assert numeric.margin == pytest.approx(analytic.margin, abs=1e-12)


def test_teleportation_fidelity_rejects_out_of_range_p():
    with pytest.raises(ValueError, match="werner_p"):
        teleportation_fidelity(-0.1)

    with pytest.raises(ValueError, match="werner_p"):
        teleportation_fidelity(1.1)


def test_teleportation_fidelity_rejects_unknown_method():
    with pytest.raises(ValueError, match="Unknown teleportation fidelity method"):
        teleportation_fidelity(0.5, method="not-a-method")
