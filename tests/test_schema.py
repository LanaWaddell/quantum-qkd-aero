import copy
import json
import math

import pytest

import qkd.schema as schema_module
from qkd.mission import MissionConfig, simulate_fibre_sweep, simulate_pass
from qkd.run import _build_results
from qkd.run_fibre import _build_results as _build_fibre_results
from qkd.schema import (
    SchemaValidationError,
    detect_results_schema,
    load_results,
    validate_results_schema,
)


def _current_payload(samples=11):
    return _build_results(
        simulate_pass(MissionConfig(samples=samples)),
        plot_path="outputs/qkd_teleportation.png",
    )


def test_schema_validator_accepts_current_v2_output_shape():
    payload = _current_payload()

    assert detect_results_schema(payload) == "2.0"
    assert validate_results_schema(payload) is True


def test_schema_validator_rejects_v1_shape_after_cutover():
    results = {
        "teleportation": {
            "frames": 1000,
            "average_fidelity": 0.99,
            "classical_limit": 2.0 / 3.0,
            "plot": "outputs/qkd_teleportation.png",
        },
        "summary": {
            "headline_key_yield": "1282.24 Kb",
            "headline_fidelity": "0.990",
        },
    }

    with pytest.raises(SchemaValidationError):
        detect_results_schema(results)


def test_schema_validator_rejects_old_orbital_v2_stub():
    old_stub = {
        "schema_version": "2.0",
        "run_metadata": {"timestamp": "", "config_hash": "", "eve_enabled": False, "eve_type": None},
        "channel": {
            "transmittance": 0.0,
            "werner_p": 0.0,
            "intrinsic_qber": 0.0,
            "slant_range_km": None,
            "elevation_deg": None,
        },
        "bb84": {
            "sifted_key_length": 0,
            "qber": 0.0,
            "gains": {"signal": 0.0, "decoy": 0.0, "vacuum": 0.0},
            "y1_lower_bound": 0.0,
            "e1_upper_bound": 0.0,
            "secure_key_rate": 0.0,
            "decoy_anomaly_score": 0.0,
        },
        "teleportation": {
            "fidelity": 0.0,
            "singlet_fraction": 0.0,
            "classical_bound": 0.6667,
            "beats_classical": False,
            "margin": 0.0,
        },
        "chsh": {
            "S": 0.0,
            "classical_bound": 2.0,
            "tsirelson_bound": 2.8284,
            "violates": False,
            "margin": 0.0,
        },
        "physics_signals": {
            "qber": 0.0,
            "decoy_anomaly_score": 0.0,
            "chsh_margin": 0.0,
            "teleportation_margin": 0.0,
            "loss_rate": 0.0,
            "secure_key_rate": 0.0,
        },
    }

    with pytest.raises(SchemaValidationError):
        detect_results_schema(old_stub)


def test_schema_validator_recognizes_generic_length_axis_with_deep_disabled():
    payload = _current_payload()
    payload.pop("geometry")
    payload["link"]["medium"] = "fibre"
    payload["profile"]["axis"] = {
        "name": "length_km",
        "values": [0.0, 10.0, 20.0],
    }
    for path in (
        "transmittance",
        "loss_db",
        "secure_key_rate_per_pulse",
        "effective_werner_p",
        "fidelity",
    ):
        payload["profile"][path] = payload["profile"][path][:3]

    assert detect_results_schema(payload) == "2.0"
    assert validate_results_schema(payload, deep=False) is True
    with pytest.raises(SchemaValidationError, match="forbidden for length_km"):
        validate_results_schema(payload)


def test_schema_module_retires_orbital_v2_required_keys_stub():
    assert not hasattr(schema_module, "V2_REQUIRED_KEYS")


def test_schema_validator_rejects_near_miss_missing_required_key():
    payload = copy.deepcopy(_current_payload())
    del payload["profile"]["aggregates"]["min_loss_axis_value"]

    with pytest.raises(SchemaValidationError, match="min_loss_axis_value"):
        detect_results_schema(payload)


def test_deep_validator_accepts_golden_satellite_payload():
    payload = _golden_satellite_payload()

    assert validate_results_schema(payload) is True


def test_deep_validator_accepts_golden_fibre_payload():
    payload = _golden_fibre_payload()

    assert validate_results_schema(payload) is True


def test_real_fibre_pipeline_deep_validates_without_secure_key_yield_bits():
    payload = _build_fibre_results(
        simulate_fibre_sweep(),
        plot_path="outputs/qkd_fibre_sweep.png",
    )

    assert "secure_key_yield_bits" not in payload["profile"]["aggregates"]
    assert validate_results_schema(payload) is True


def test_load_results_honors_deep_flag(tmp_path):
    payload = _golden_satellite_payload()
    payload["profile"]["transmittance"][1] = 1.4
    path = tmp_path / "results.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_results(path, deep=False)["schema_version"] == "2.0"
    with pytest.raises(SchemaValidationError, match="profile.transmittance"):
        load_results(path)


def test_declared_schema_extension_allows_explicit_extra_key(monkeypatch):
    payload = _golden_satellite_payload()
    payload["link"]["future_axis"] = "declared"

    with pytest.raises(SchemaValidationError, match="Undeclared schema key"):
        validate_results_schema(payload)

    monkeypatch.setitem(schema_module.DECLARED_SCHEMA_EXTENSIONS, "link", {"future_axis"})
    payload["provenance"]["link.future_axis"] = "DERIVED"

    assert validate_results_schema(payload) is True


@pytest.mark.parametrize(
    ("payload_factory", "mutate", "match"),
    [
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["profile"]["transmittance"].__setitem__(1, 1.4),
            "profile.transmittance",
            id="out_of_range_transmittance_element",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["profile"]["fidelity"].__setitem__(1, float("nan")),
            "profile.fidelity",
            id="nan_array_element",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["teleportation"].__setitem__("average_fidelity", float("inf")),
            "teleportation.average_fidelity",
            id="inf_scalar",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["profile"].__setitem__("loss_db", "wrong"),
            "profile.loss_db",
            id="wrong_type_array",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["profile"]["loss_db"].pop(),
            "same length",
            id="length_mismatch",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["teleportation"].__setitem__("classical_limit", 0.5),
            "teleportation.classical_limit",
            id="wrong_constant",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["profile"]["loss_db"].__setitem__(1, 11.0),
            "profile.loss_db",
            id="inconsistent_k1_loss",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["profile"]["aggregates"].__setitem__("min_loss_db", 99.0),
            "profile.aggregates.min_loss_db",
            id="inconsistent_k2_min_loss",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["teleportation"].__setitem__("average_fidelity", 0.901),
            "teleportation.average_fidelity",
            id="inconsistent_k5_rounded_fidelity",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["teleportation"].__setitem__("frames", 99),
            "teleportation.frames",
            id="inconsistent_k10_frames",
        ),
        pytest.param(
            (lambda: _golden_fibre_payload()),
            lambda p: p["profile"]["aggregates"]["secure_distance_bracket"].__setitem__(
                "last_positive_length_km",
                10.0,
            ),
            "secure_distance_bracket",
            id="inconsistent_k8_fibre_bracket",
        ),
        pytest.param(
            (lambda: _golden_fibre_payload()),
            lambda p: p["profile"]["aggregates"].__setitem__("secure_key_yield_bits", 1.0),
            "forbidden for length_km",
            id="fibre_forbids_secure_key_yield",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["profile"]["aggregates"].pop("secure_key_yield_bits"),
            "required for time_s",
            id="satellite_requires_secure_key_yield",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["link"].__setitem__("medium", "free_space"),
            "link.medium",
            id="unknown_link_medium",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["profile"].__setitem__("extra_curve", []),
            "Undeclared schema key",
            id="undeclared_extra_key",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["provenance"].pop("profile.loss_db"),
            "Missing provenance",
            id="missing_provenance_tag",
        ),
        pytest.param(
            (lambda: _golden_satellite_payload()),
            lambda p: p["mission"]["detector"].pop("dark_count_prob"),
            "dark_count_prob",
            id="near_miss_missing_key",
        ),
    ],
)
def test_deep_validator_rejects_mutated_payloads(payload_factory, mutate, match):
    payload = payload_factory()
    mutate(payload)

    with pytest.raises(SchemaValidationError, match=match):
        validate_results_schema(payload)


def _golden_satellite_payload():
    # Contract derivations:
    #   loss_db[i] = -10*log10(transmittance[i])
    #   fidelity[i] = (1 + effective_werner_p[i]) / 2
    #   secure_key_yield_bits = sum(rate_i * f_rep * dt)
    axis_values = [0.0, 1.0, 2.0]
    transmittance = [0.01, 0.1, 0.04]
    loss_db = [_loss_db(eta) for eta in transmittance]
    rates = [0.01, 0.02, 0.03]
    effective_werner_p = [0.8, 0.9, 0.7]
    fidelity = [_werner_fidelity(p_eff) for p_eff in effective_werner_p]
    min_loss_index = min(range(len(loss_db)), key=loss_db.__getitem__)
    pulse_repetition_rate_hz = 100.0
    dt = (axis_values[-1] - axis_values[0]) / (len(axis_values) - 1)
    secure_key_yield_bits = sum(rate * pulse_repetition_rate_hz * dt for rate in rates)
    elevation_deg = [10.0, 80.0, 20.0]
    slant_range_km = [1200.0, 550.0, 900.0]
    mean_fidelity = sum(fidelity) / len(fidelity)

    payload = {
        "schema_version": "2.0",
        "link": {
            "medium": "atmospheric",
            "topology": "point_to_point",
            "protocol": "decoy_bb84",
        },
        "teleportation": {
            "frames": len(axis_values),
            "average_fidelity": round(mean_fidelity, 3),
            "classical_limit": 2.0 / 3.0,
            "plot": "outputs/qkd_teleportation.png",
        },
        "summary": {
            "headline_key_yield": "0.01 Kb",
            "headline_fidelity": "0.900",
        },
        "profile": {
            "axis": {"name": "time_s", "values": axis_values},
            "transmittance": transmittance,
            "loss_db": loss_db,
            "secure_key_rate_per_pulse": rates,
            "effective_werner_p": effective_werner_p,
            "fidelity": fidelity,
            "aggregates": {
                "min_loss_db": loss_db[min_loss_index],
                "min_loss_axis_value": axis_values[min_loss_index],
                "secure_key_yield_bits": secure_key_yield_bits,
                "mean_fidelity": mean_fidelity,
            },
        },
        "geometry": {
            "elevation_deg": elevation_deg,
            "slant_range_km": slant_range_km,
            "min_loss": {
                "elevation_deg": elevation_deg[min_loss_index],
                "slant_range_km": slant_range_km[min_loss_index],
            },
        },
        "mission": _mission_inputs(pulse_repetition_rate_hz),
        "run_metadata": {
            "generator": "test_schema.py",
            "pipeline": "golden.satellite",
            "physics_mode": "computed",
        },
    }
    payload["provenance"] = _provenance_for(payload)
    return payload


def _golden_fibre_payload():
    # Contract derivations:
    #   length_km forbids secure_key_yield_bits because the axis is distance.
    #   max_secure_distance_km is the last sample with positive SKR; the bracket
    #   records that sample and the immediately following zero-floor sample.
    axis_values = [0.0, 10.0, 20.0, 25.0]
    transmittance = [0.2, 0.1, 0.02, 0.01]
    loss_db = [_loss_db(eta) for eta in transmittance]
    rates = [0.02, 0.01, 0.001, 0.0]
    effective_werner_p = [0.98, 0.98, 0.98, 0.98]
    fidelity = [_werner_fidelity(p_eff) for p_eff in effective_werner_p]
    min_loss_index = min(range(len(loss_db)), key=loss_db.__getitem__)
    mean_fidelity = sum(fidelity) / len(fidelity)

    payload = {
        "schema_version": "2.0",
        "link": {
            "medium": "fibre",
            "topology": "point_to_point",
            "protocol": "decoy_bb84",
        },
        "teleportation": {
            "frames": len(axis_values),
            "average_fidelity": round(mean_fidelity, 3),
            "classical_limit": 2.0 / 3.0,
            "plot": "outputs/qkd_fibre_sweep.png",
        },
        "summary": {
            "headline_key_yield": "2.000e-02 bits/pulse @ 0.0 km",
            "headline_fidelity": "0.990",
            "headline_max_secure_distance": "20.0 km",
        },
        "profile": {
            "axis": {"name": "length_km", "values": axis_values},
            "transmittance": transmittance,
            "loss_db": loss_db,
            "secure_key_rate_per_pulse": rates,
            "effective_werner_p": effective_werner_p,
            "fidelity": fidelity,
            "aggregates": {
                "min_loss_db": loss_db[min_loss_index],
                "min_loss_axis_value": axis_values[min_loss_index],
                "mean_fidelity": mean_fidelity,
                "max_secure_distance_km": 20.0,
                "secure_distance_bracket": {
                    "last_positive_length_km": 20.0,
                    "last_positive_secure_key_rate_per_pulse": 0.001,
                    "first_non_positive_length_km": 25.0,
                    "first_non_positive_secure_key_rate_per_pulse": 0.0,
                },
            },
        },
        "mission": {
            **_mission_inputs(100.0),
            "fibre": {
                "attenuation_db_km": 0.2,
                "fixed_loss_db": 6.0,
                "intrinsic_qber": 0.015,
                "dark_count_prob": 1e-6,
                "werner_p": 0.98,
            },
        },
        "run_metadata": {
            "generator": "test_schema.py",
            "pipeline": "golden.fibre",
            "physics_mode": "computed",
            "max_secure_distance_definition": (
                "last length sample with positive secure_key_rate_per_pulse; "
                "secure_distance_bracket records the first non-positive sample"
            ),
        },
    }
    payload["provenance"] = _provenance_for(payload)
    return payload


def _mission_inputs(pulse_repetition_rate_hz):
    return {
        "pulse_repetition_rate_hz": pulse_repetition_rate_hz,
        "intensities": {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0},
        "detector": {
            "detection_efficiency": 0.5,
            "dark_count_prob": 1e-6,
            "error_correction_efficiency": 1.16,
        },
        "sky_condition": "night",
    }


def _loss_db(transmittance):
    return -10.0 * math.log10(transmittance)


def _werner_fidelity(werner_p):
    return (1.0 + werner_p) / 2.0


def _provenance_for(payload):
    return {
        path: "DERIVED"
        for path in _leaf_paths(payload)
        if not path.startswith(("schema_version", "provenance", "run_metadata"))
    }


def _leaf_paths(value, prefix=""):
    if isinstance(value, dict):
        paths = set()
        for key, child in value.items():
            child_prefix = key if not prefix else f"{prefix}.{key}"
            paths.update(_leaf_paths(child, child_prefix))
        return paths
    return {prefix}
