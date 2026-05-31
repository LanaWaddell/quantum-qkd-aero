import pytest

from qkd.schema import SchemaValidationError, detect_results_schema, validate_results_schema


def test_schema_validator_accepts_current_v1_output_shape():
    results = {
        "teleportation": {
            "frames": 1000,
            "average_fidelity": 0.851,
            "classical_limit": 0.67,
            "remaining_entangled_resource_kb": 5.0,
            "plot": "outputs/qkd_teleportation.png",
        },
        "summary": {
            "headline_key_yield": "5.00 Kb",
            "headline_fidelity": "0.851",
        },
    }

    assert detect_results_schema(results) == "1"
    assert validate_results_schema(results) is True


def test_schema_validator_accepts_future_v2_contract_shape():
    results = {
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

    assert detect_results_schema(results) == "2.0"
    assert validate_results_schema(results) is True


def test_schema_validator_rejects_unknown_shape():
    with pytest.raises(SchemaValidationError):
        detect_results_schema({"summary": {}})
