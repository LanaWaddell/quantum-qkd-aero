import copy

import pytest

import qkd.schema as schema_module
from qkd.mission import MissionConfig, simulate_pass
from qkd.run import _build_results
from qkd.schema import SchemaValidationError, detect_results_schema, validate_results_schema


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


def test_schema_validator_accepts_generic_length_axis_without_geometry():
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
    assert validate_results_schema(payload) is True


def test_schema_module_retires_orbital_v2_required_keys_stub():
    assert not hasattr(schema_module, "V2_REQUIRED_KEYS")


def test_schema_validator_rejects_near_miss_missing_required_key():
    payload = copy.deepcopy(_current_payload())
    del payload["profile"]["aggregates"]["min_loss_axis_value"]

    with pytest.raises(SchemaValidationError, match="min_loss_axis_value"):
        detect_results_schema(payload)
