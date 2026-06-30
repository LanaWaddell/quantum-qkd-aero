import copy

import pytest

from qkd.mission import INTENSITIES, MissionConfig, PULSE_REPETITION_RATE_HZ, simulate_pass
from qkd.provenance import Provenance, ProvenanceValidationError, validate_provenance
from qkd.run import _build_results
from qkd.signals import DetectorParams


def _payload(config=None):
    result = simulate_pass(config)
    return result, _build_results(result, plot_path="outputs/qkd_teleportation.png")


def test_provenance_declares_in_use_and_reserved_tags():
    assert {tag.value for tag in Provenance} == {
        "ANALYTIC",
        "SIMULATED",
        "DERIVED",
        "ILLUSTRATIVE",
        "MEASURED",
        "ESTIMATED",
        "VALIDATED",
    }


def test_default_pass_does_not_apply_reserved_provenance_tags():
    reserved = {
        Provenance.MEASURED.value,
        Provenance.ESTIMATED.value,
        Provenance.VALIDATED.value,
    }

    result = simulate_pass()

    assert reserved.isdisjoint(set(result.provenance.values()))


def test_validate_provenance_accepts_real_emission_and_does_not_mutate_payload():
    _, payload = _payload(MissionConfig(samples=11))
    original_payload = copy.deepcopy(payload)
    original_provenance = copy.deepcopy(payload["provenance"])

    assert validate_provenance(payload, payload["provenance"]) is True
    assert payload == original_payload
    assert payload["provenance"] == original_provenance


def test_validate_provenance_treats_arrays_as_single_leaves():
    emitted = {
        "profile": {"loss_db": [3.0, 2.0, 3.0]},
        "run_metadata": {"generator": "unit-test"},
        "provenance": {},
    }

    assert validate_provenance(emitted, {"profile.loss_db": Provenance.SIMULATED.value}) is True
    with pytest.raises(ProvenanceValidationError):
        validate_provenance(emitted, {"profile.loss_db.0": Provenance.SIMULATED.value})


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda payload: payload["provenance"].pop("teleportation.frames"),
            "Missing provenance tags",
        ),
        (
            lambda payload: payload["provenance"].__setitem__(
                "profile.non_emitted_field",
                Provenance.DERIVED.value,
            ),
            "non-emitted fields",
        ),
        (
            lambda payload: payload["provenance"].__setitem__(
                "teleportation.frames",
                "HANDWAVED",
            ),
            "Unknown provenance tag",
        ),
        (
            lambda payload: payload["provenance"].__setitem__(
                "teleportation.frames",
                Provenance.MEASURED.value,
            ),
            "Reserved provenance tag",
        ),
    ],
)
def test_validate_provenance_rejects_invalid_maps(mutator, message):
    _, payload = _payload(MissionConfig(samples=11))
    mutator(payload)

    with pytest.raises(ProvenanceValidationError, match=message):
        validate_provenance(payload, payload["provenance"])


def test_illustrative_mission_inputs_are_emitted_and_fully_tagged():
    config = MissionConfig(
        samples=11,
        detector=DetectorParams(
            detection_efficiency=0.6,
            dark_count_prob=2.0e-6,
            error_correction_efficiency=1.2,
        ),
    )
    _, payload = _payload(config)
    mission = payload["mission"]
    provenance = payload["provenance"]

    assert mission["pulse_repetition_rate_hz"] == PULSE_REPETITION_RATE_HZ
    assert mission["intensities"] == INTENSITIES
    assert mission["detector"] == {
        "detection_efficiency": 0.6,
        "dark_count_prob": 2.0e-6,
        "error_correction_efficiency": 1.2,
    }
    assert mission["sky_condition"] == "night"

    for path in {
        "link.medium",
        "link.topology",
        "link.protocol",
        "profile.axis.name",
    }:
        assert provenance[path] == Provenance.ILLUSTRATIVE.value

    detector_paths = {
        "mission.detector.detection_efficiency",
        "mission.detector.dark_count_prob",
        "mission.detector.error_correction_efficiency",
    }
    for path in {
        "mission.pulse_repetition_rate_hz",
        "mission.intensities.signal",
        "mission.intensities.decoy",
        "mission.intensities.vacuum",
        "mission.sky_condition",
        *detector_paths,
    }:
        assert provenance[path] == Provenance.ILLUSTRATIVE.value

    assert "mission.intensities" not in provenance
    assert "mission.detector" not in provenance
    assert validate_provenance(payload, provenance) is True


def test_analytic_classical_limit_is_exactly_tagged():
    _, payload = _payload(MissionConfig(samples=11))

    assert payload["teleportation"]["classical_limit"] == 2.0 / 3.0
    assert payload["provenance"]["teleportation.classical_limit"] == Provenance.ANALYTIC.value


def test_simulated_pass_arrays_change_when_physical_geometry_changes():
    _, low_pass = _payload(MissionConfig(samples=31, altitude_km=550.0, sky_condition="day"))
    _, high_pass = _payload(MissionConfig(samples=31, altitude_km=700.0, sky_condition="day"))

    for path in (
        "transmittance",
        "secure_key_rate_per_pulse",
        "effective_werner_p",
        "fidelity",
    ):
        assert low_pass["profile"][path] != high_pass["profile"][path]
        assert low_pass["provenance"][f"profile.{path}"] == Provenance.SIMULATED.value

    assert low_pass["profile"]["loss_db"] != high_pass["profile"]["loss_db"]
    assert low_pass["provenance"]["profile.loss_db"] == Provenance.DERIVED.value
    assert low_pass["geometry"]["elevation_deg"] != high_pass["geometry"]["elevation_deg"]
    assert low_pass["provenance"]["geometry.elevation_deg"] == Provenance.SIMULATED.value


def test_derived_values_recompute_from_emitted_components():
    _, payload = _payload(MissionConfig(samples=31))
    profile = payload["profile"]
    geometry = payload["geometry"]
    mission = payload["mission"]
    summary = payload["summary"]
    teleportation = payload["teleportation"]

    axis_values = profile["axis"]["values"]
    dt = (axis_values[-1] - axis_values[0]) / (len(axis_values) - 1)
    expected_yield = sum(
        rate * mission["pulse_repetition_rate_hz"] * dt
        for rate in profile["secure_key_rate_per_pulse"]
    )
    expected_mean_fidelity = sum(profile["fidelity"]) / len(profile["fidelity"])
    min_loss_index = min(range(len(profile["loss_db"])), key=profile["loss_db"].__getitem__)

    assert profile["aggregates"]["secure_key_yield_bits"] == pytest.approx(expected_yield, abs=1e-9)
    assert profile["aggregates"]["mean_fidelity"] == pytest.approx(expected_mean_fidelity, abs=1e-15)
    assert profile["aggregates"]["min_loss_db"] == profile["loss_db"][min_loss_index]
    assert profile["aggregates"]["min_loss_axis_value"] == axis_values[min_loss_index]
    assert geometry["min_loss"]["elevation_deg"] == geometry["elevation_deg"][min_loss_index]
    assert geometry["min_loss"]["slant_range_km"] == geometry["slant_range_km"][min_loss_index]
    assert summary["headline_key_yield"] == f"{expected_yield / 1_000.0:.2f} Kb"
    assert summary["headline_fidelity"] == f"{expected_mean_fidelity:.3f}"
    assert teleportation["average_fidelity"] == round(expected_mean_fidelity, 3)

    for path in (
        "profile.loss_db",
        "profile.aggregates.min_loss_db",
        "profile.aggregates.min_loss_axis_value",
        "profile.aggregates.secure_key_yield_bits",
        "profile.aggregates.mean_fidelity",
        "geometry.min_loss.elevation_deg",
        "geometry.min_loss.slant_range_km",
        "summary.headline_key_yield",
        "summary.headline_fidelity",
        "teleportation.average_fidelity",
    ):
        assert payload["provenance"][path] == Provenance.DERIVED.value


def test_provenance_is_deterministic_for_identical_inputs():
    _, first = _payload(MissionConfig(samples=11))
    _, second = _payload(MissionConfig(samples=11))

    assert first["provenance"] == second["provenance"]
