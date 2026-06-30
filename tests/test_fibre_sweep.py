import hashlib
import inspect
import json

import pytest

from qkd.fibre import DEFAULT_FIBRE
from qkd.mission import simulate_fibre_sweep, simulate_profile
from qkd.provenance import validate_provenance
import qkd.run as run_module
import qkd.run_fibre as run_fibre_module
from qkd.schema import validate_results_schema


EXPECTED_SATELLITE_V2_STABLE_SHA256 = (
    "bcac8a7024ccd114a0ef5288466ef8ab43f08964d61dada8d1cc7bdef28c8962"
)


def test_fibre_sweep_emits_valid_v2_without_geometry():
    result = simulate_fibre_sweep()
    payload = run_fibre_module._build_results(
        result,
        plot_path="outputs/qkd_fibre_sweep.png",
    )

    assert validate_results_schema(payload) is True
    assert validate_provenance(payload, payload["provenance"]) is True
    assert payload["link"] == {
        "medium": "fibre",
        "topology": "point_to_point",
        "protocol": "decoy_bb84",
    }
    assert payload["profile"]["axis"]["name"] == "length_km"
    assert "geometry" not in payload
    assert not any(path.startswith("geometry.") for path in payload["provenance"])


def test_satellite_emission_remains_pr_b_stable_hash(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_module, "OUTPUTS_DIR", str(tmp_path))

    run_module.main()

    payload = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    capsys.readouterr()

    assert _stable_json_hash(payload) == EXPECTED_SATELLITE_V2_STABLE_SHA256
    assert payload["link"]["medium"] == "atmospheric"
    assert payload["profile"]["axis"]["name"] == "time_s"


def test_fibre_sweep_rate_distance_curve_is_monotone_and_brackets_cutoff():
    result = simulate_fibre_sweep()
    rates = result.secure_key_rate_per_pulse

    assert all(left >= right for left, right in zip(rates, rates[1:]))
    assert any(rate > 0.0 for rate in rates)
    assert any(rate == 0.0 for rate in rates)
    assert result.secure_distance_bracket.last_positive_length_km == 190.0
    assert result.secure_distance_bracket.first_non_positive_length_km == 195.0


def test_max_secure_distance_is_last_positive_sample_with_auditable_bracket():
    result = simulate_fibre_sweep()
    payload = run_fibre_module._build_results(
        result,
        plot_path="outputs/qkd_fibre_sweep.png",
    )
    aggregates = payload["profile"]["aggregates"]
    bracket = aggregates["secure_distance_bracket"]

    assert aggregates["max_secure_distance_km"] == 190.0
    assert bracket["last_positive_length_km"] == aggregates["max_secure_distance_km"]
    assert bracket["last_positive_secure_key_rate_per_pulse"] > 0.0
    assert bracket["first_non_positive_length_km"] == 195.0
    assert bracket["first_non_positive_secure_key_rate_per_pulse"] == 0.0
    assert payload["summary"]["headline_max_secure_distance"] == "190.0 km"
    assert "last length sample with positive" in payload["run_metadata"][
        "max_secure_distance_definition"
    ]


def test_dark_fibre_sweep_preserves_source_werner_p():
    result = simulate_fibre_sweep()

    assert result.werner_p_source == DEFAULT_FIBRE["werner_p"]
    assert result.effective_werner_p
    assert all(
        p_eff == pytest.approx(DEFAULT_FIBRE["werner_p"], rel=0.0, abs=1e-12)
        for p_eff in result.effective_werner_p
    )


def test_fibre_sweep_is_deterministic_and_uses_unmodified_profile_core():
    first = simulate_fibre_sweep()
    second = simulate_fibre_sweep()

    assert first == second
    assert first.provenance == second.provenance
    source = inspect.getsource(simulate_profile)
    assert "fibre_channel_state" not in source
    assert "length_km" not in source


def test_run_fibre_writes_valid_v2_artifact(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_fibre_module, "OUTPUTS_DIR", str(tmp_path))

    run_fibre_module.main()

    payload = json.loads((tmp_path / "fibre_results.json").read_text(encoding="utf-8"))
    printed = capsys.readouterr().out.strip()

    assert (tmp_path / "qkd_fibre_sweep.png").exists()
    assert validate_results_schema(payload) is True
    assert validate_provenance(payload, payload["provenance"]) is True
    assert payload["profile"]["aggregates"]["max_secure_distance_km"] == 190.0
    assert printed == (
        "Fibre Sweep Updated: Max secure distance 190.0 km | "
        "SKR@0 km 1.227e-02 bits/pulse"
    )


def _stable_json_hash(payload):
    stable_text = json.dumps(
        _stable_json_value(payload),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(stable_text.encode("utf-8")).hexdigest()


def _stable_json_value(value):
    if isinstance(value, float):
        return format(value, ".12g")
    if isinstance(value, list):
        return [_stable_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _stable_json_value(value[key]) for key in sorted(value)}
    return value
