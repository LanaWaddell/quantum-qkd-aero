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
from qkd.run import _build_results
from qkd.signals import ChannelState, DetectorParams
from qkd.teleportation import teleportation_fidelity


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pr_a_pre_refactor_satellite_output.json"


def _fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_simulate_pass_matches_captured_pre_refactor_pass_result():
    fixture = _fixture()

    assert asdict(simulate_pass()) == fixture["pass_result"]


def test_emitted_results_match_captured_pre_refactor_bytes():
    fixture = _fixture()
    result = simulate_pass()
    payload = _build_results(result, plot_path="outputs/qkd_teleportation.png")
    headline = (
        "Dashboard Updated: "
        f"Min loss {result.min_loss_db:.1f} dB | "
        f"Fidelity {result.mean_fidelity:.3f}"
    )

    assert payload == fixture["emitted_results"]
    assert json.dumps(payload) == fixture["emitted_results_json"]
    assert headline == fixture["headline"]
    assert validate_provenance(payload, payload["provenance"]) is True


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
