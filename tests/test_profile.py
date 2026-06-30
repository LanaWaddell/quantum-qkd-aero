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
    "bcac8a7024ccd114a0ef5288466ef8ab43f08964d61dada8d1cc7bdef28c8962"
)
V1_DATA_TO_V2_PATHS = {
    "teleportation.frames": "teleportation.frames",
    "teleportation.average_fidelity": "teleportation.average_fidelity",
    "teleportation.classical_limit": "teleportation.classical_limit",
    "teleportation.plot": "teleportation.plot",
    "summary.headline_key_yield": "summary.headline_key_yield",
    "summary.headline_fidelity": "summary.headline_fidelity",
    "pass_profile.time_s": "profile.axis.values",
    "pass_profile.elevation_deg": "geometry.elevation_deg",
    "pass_profile.slant_range_km": "geometry.slant_range_km",
    "pass_profile.transmittance": "profile.transmittance",
    "pass_profile.loss_db": "profile.loss_db",
    "pass_profile.secure_key_rate_per_pulse": "profile.secure_key_rate_per_pulse",
    "pass_profile.effective_werner_p": "profile.effective_werner_p",
    "pass_profile.fidelity": "profile.fidelity",
    "pass_profile.min_loss_db": "profile.aggregates.min_loss_db",
    "pass_profile.min_loss_time_s": "profile.aggregates.min_loss_axis_value",
    "pass_profile.min_loss_elevation_deg": "geometry.min_loss.elevation_deg",
    "pass_profile.min_loss_slant_range_km": "geometry.min_loss.slant_range_km",
    "pass_profile.secure_key_yield_bits": "profile.aggregates.secure_key_yield_bits",
    "pass_profile.mean_fidelity": "profile.aggregates.mean_fidelity",
    "mission.pulse_repetition_rate_hz": "mission.pulse_repetition_rate_hz",
    "mission.intensities.signal": "mission.intensities.signal",
    "mission.intensities.decoy": "mission.intensities.decoy",
    "mission.intensities.vacuum": "mission.intensities.vacuum",
    "mission.detector.detection_efficiency": "mission.detector.detection_efficiency",
    "mission.detector.dark_count_prob": "mission.detector.dark_count_prob",
    "mission.detector.error_correction_efficiency": "mission.detector.error_correction_efficiency",
    "mission.sky_condition": "mission.sky_condition",
    "run_metadata.generator": "run_metadata.generator",
    "run_metadata.pipeline": "run_metadata.pipeline",
    "run_metadata.physics_mode": "run_metadata.physics_mode",
}
V1_TO_V2_PATHS = {
    **V1_DATA_TO_V2_PATHS,
    **{
        f"provenance.{v1_path}": f"provenance.{v2_path}"
        for v1_path, v2_path in V1_DATA_TO_V2_PATHS.items()
        if not v1_path.startswith("run_metadata.")
    },
}
NEW_V2_LEAF_PATHS = {
    "schema_version",
    "link.medium",
    "link.topology",
    "link.protocol",
    "profile.axis.name",
    "provenance.link.medium",
    "provenance.link.topology",
    "provenance.link.protocol",
    "provenance.profile.axis.name",
}


def _fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_simulate_pass_physics_matches_captured_pre_refactor_pass_result():
    fixture = _fixture()
    actual = asdict(simulate_pass())
    expected = dict(fixture["pass_result"])

    actual.pop("provenance")
    expected.pop("provenance")
    _assert_close_structure(actual, expected)


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

    assert emitted_payload["schema_version"] == "2.0"
    assert emitted_payload["link"] == {
        "medium": "atmospheric",
        "topology": "point_to_point",
        "protocol": "decoy_bb84",
    }
    assert emitted_payload["profile"]["axis"]["name"] == "time_s"
    assert emitted_payload["teleportation"]["plot"] == fixture["emitted_results"]["teleportation"]["plot"]
    assert _stable_json_hash(emitted_payload) == EXPECTED_EMITTED_RESULTS_STABLE_SHA256
    assert printed_headline == fixture["headline"]
    assert validate_provenance(emitted_payload, emitted_payload["provenance"]) is True


def test_v2_parity_map_covers_all_v1_fixture_leaves(tmp_path, monkeypatch, capsys):
    fixture = _fixture()
    monkeypatch.setattr(run_module, "OUTPUTS_DIR", str(tmp_path))

    run_module.main()

    v1_payload = fixture["emitted_results"]
    v2_payload = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    capsys.readouterr()

    v1_leaf_paths = _leaf_paths(v1_payload)
    v2_leaf_paths = _leaf_paths(v2_payload)

    assert set(V1_TO_V2_PATHS) == v1_leaf_paths
    assert set(V1_TO_V2_PATHS.values()) | NEW_V2_LEAF_PATHS == v2_leaf_paths

    for v1_path, v2_path in V1_TO_V2_PATHS.items():
        _assert_close_structure(
            _get_path(v2_payload, v2_path),
            _get_path(v1_payload, v1_path),
            f"{v1_path} -> {v2_path}",
        )


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


def _leaf_paths(payload, prefix=""):
    if isinstance(payload, dict):
        if prefix == "provenance":
            return {f"provenance.{key}" for key in payload}
        paths = set()
        for key, value in payload.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            paths.update(_leaf_paths(value, child_prefix))
        return paths
    return {prefix}


def _get_path(payload, path):
    parts = path.split(".")
    if parts[0] == "provenance":
        return payload["provenance"][".".join(parts[1:])]

    value = payload
    for part in parts:
        value = value[part]
    return value


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
