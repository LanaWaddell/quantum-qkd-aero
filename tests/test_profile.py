import hashlib
import inspect
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from qkd.mission import (
    INTENSITIES,
    PULSE_REPETITION_RATE_HZ,
    simulate_pass,
    simulate_profile,
)
from qkd.provenance import validate_provenance
import qkd.run as run_module
from qkd.signals import ChannelState, DetectorParams
from qkd.teleportation import teleportation_fidelity


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pr_a_pre_refactor_satellite_output.json"
FLOAT_REL_TOL = 1e-12
FLOAT_ABS_TOL = 1e-12
EXPECTED_EMITTED_RESULTS_STABLE_SHA256 = (
    "5e24f984776a1906e65ee588557f5256ac6b547995c8e43c16ee0bd0e33b5612"
)


def _fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_simulate_pass_matches_captured_pre_refactor_pass_result():
    fixture = _fixture()

    _assert_close_structure(asdict(simulate_pass()), fixture["pass_result"])


def test_run_main_emitted_results_match_captured_pre_refactor_contract(
    tmp_path,
    monkeypatch,
    capsys,
):
    fixture = _fixture()
    monkeypatch.setattr(run_module, "OUTPUTS_DIR", str(tmp_path))

    run_module.main()

    emitted_text = (tmp_path / "results.json").read_text(encoding="utf-8")
    emitted_payload = json.loads(emitted_text)
    printed_headline = capsys.readouterr().out.strip()

    assert emitted_payload["teleportation"]["plot"] == "outputs/qkd_teleportation.png"
    assert emitted_payload["teleportation"]["plot"] == fixture["emitted_results"]["teleportation"]["plot"]
    assert _stable_json_hash(fixture["emitted_results"]) == EXPECTED_EMITTED_RESULTS_STABLE_SHA256
    assert _stable_json_hash(emitted_payload) == EXPECTED_EMITTED_RESULTS_STABLE_SHA256
    assert printed_headline == fixture["headline"]
    assert validate_provenance(emitted_payload, emitted_payload["provenance"]) is True


def test_simulate_pass_remains_deterministic_after_profile_delegation():
    first = simulate_pass()
    second = simulate_pass()

    assert first == second
    assert first.provenance == second.provenance


def test_simulate_profile_composes_synthetic_channel_sequence_without_geometry():
    axis_values = [0.0, 10.0, 20.0]
    channel_states = [
        ChannelState(transmittance=0.02, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=1e-6),
        ChannelState(transmittance=0.08, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=1e-6),
        ChannelState(transmittance=0.04, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=1e-6),
    ]

    profile = simulate_profile(
        axis_values,
        channel_states,
        intensities=INTENSITIES,
        n_pulses=1_000_000,
        detector=DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6),
        pulse_repetition_rate_hz=PULSE_REPETITION_RATE_HZ,
        sky_condition="night",
    )

    assert profile.axis_values == axis_values
    assert profile.transmittance == [state.transmittance for state in channel_states]
    assert profile.min_loss_index == 1
    assert profile.min_loss_db == min(profile.loss_db)
    assert len(profile.secure_key_rate_per_pulse) == len(axis_values)
    assert len(profile.effective_werner_p) == len(axis_values)
    assert len(profile.fidelity) == len(axis_values)
    assert profile.secure_key_yield_bits > 0.0
    assert profile.mean_fidelity == pytest.approx(sum(profile.fidelity) / len(profile.fidelity))
    assert profile.classical_bound == teleportation_fidelity(0.98).classical_bound


def test_simulate_profile_source_has_no_satellite_geometry_dependencies():
    source = inspect.getsource(simulate_profile)

    assert "satellite_pass" not in source
    assert "orbit" not in source
    assert "elevation" not in source
    assert "slant_range" not in source


def _assert_close_structure(actual, expected, path="root"):
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert actual.keys() == expected.keys(), path
        for key in expected:
            _assert_close_structure(actual[key], expected[key], f"{path}.{key}")
        return

    if isinstance(expected, list):
        assert isinstance(actual, list), path
        assert len(actual) == len(expected), path
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            _assert_close_structure(actual_item, expected_item, f"{path}[{index}]")
        return

    if isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL), path
        return

    assert actual == expected, path


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
