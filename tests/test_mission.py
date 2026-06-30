from dataclasses import fields
from pathlib import Path

import pytest

from qkd.bb84 import run_decoy_bb84
from qkd.channel import channel_state
from qkd.mission import (
    INTENSITIES,
    MissionConfig,
    PULSE_REPETITION_RATE_HZ,
    simulate_pass,
)
from qkd.provenance import Provenance, validate_provenance
from qkd.run import _build_results
from qkd.schema import detect_results_schema
from qkd.signals import ChannelState, DetectorParams, PhysicsSignals
from qkd.teleportation import teleportation_fidelity


def test_secure_key_yield_is_integral_of_per_sample_rates():
    result = simulate_pass()
    dt = (result.time_s[-1] - result.time_s[0]) / (len(result.time_s) - 1)
    expected_yield = sum(
        rate * PULSE_REPETITION_RATE_HZ * dt
        for rate in result.secure_key_rate_per_pulse
    )

    assert result.secure_key_yield_bits == pytest.approx(expected_yield, abs=1e-9)
    assert result.secure_key_yield_bits != 5_000.0


def test_secure_key_yield_zero_when_all_sample_rates_collapse():
    config = MissionConfig(atmosphere={"system_efficiency": 0.0})

    result = simulate_pass(config)

    assert all(rate == 0.0 for rate in result.secure_key_rate_per_pulse)
    assert result.secure_key_yield_bits == 0.0
    assert result.provenance["summary.headline_key_yield"] == Provenance.DERIVED.value


def test_detector_efficiency_is_composed_once_and_channel_is_unchanged():
    state = channel_state(elevation_deg=90.0, slant_range_km=550.0)
    repeated_state = channel_state(elevation_deg=90.0, slant_range_km=550.0)
    full_detector = DetectorParams(detection_efficiency=0.8, dark_count_prob=0.0)
    half_detector = DetectorParams(detection_efficiency=0.4, dark_count_prob=0.0)

    full = run_decoy_bb84(state, INTENSITIES, 1_000_000, full_detector)
    half = run_decoy_bb84(state, INTENSITIES, 1_000_000, half_detector)
    y1_true_full = state.transmittance * full_detector.detection_efficiency
    y1_true_half = state.transmittance * half_detector.detection_efficiency

    assert repeated_state.transmittance == state.transmittance
    assert y1_true_half == pytest.approx(y1_true_full / 2.0, rel=0.0, abs=1e-15)
    assert half.q1 == pytest.approx(full.q1 / 2.0, rel=0.0, abs=1e-8)
    assert half.secure_key_rate == pytest.approx(full.secure_key_rate / 2.0, rel=0.0, abs=1e-8)


def test_daytime_fidelity_arches_over_strongest_link_and_dips_below_classical():
    result = simulate_pass(MissionConfig(sky_condition="day", samples=101))
    peak = result.min_loss_index

    assert peak == result.fidelity.index(max(result.fidelity))
    assert result.fidelity[0] < result.fidelity[peak]
    assert result.fidelity[-1] < result.fidelity[peak]
    assert result.fidelity[0] < result.classical_bound
    assert result.fidelity[-1] < result.classical_bound


def test_night_fidelity_is_flat_at_single_source_werner_p_including_horizon():
    result = simulate_pass(MissionConfig(sky_condition="night", samples=101))
    expected = teleportation_fidelity(result.werner_p_source).fidelity

    assert result.werner_p_source == pytest.approx(0.98, abs=1e-15)
    assert all(p_eff == pytest.approx(result.werner_p_source, abs=1e-15) for p_eff in result.effective_werner_p)
    assert all(fid == pytest.approx(expected, abs=1e-9) for fid in result.fidelity)


def test_default_headline_values_remain_computed_and_stable():
    result = simulate_pass()

    assert result.min_loss_db == pytest.approx(27.7, abs=0.05)
    assert result.mean_fidelity == pytest.approx(0.990, abs=1e-12)


def test_v2_results_shape_drops_dead_key_and_accepts_metadata():
    result = simulate_pass(MissionConfig(samples=11))
    payload = _build_results(result, plot_path="outputs/qkd_teleportation.png")

    assert "remaining_entangled_resource_kb" not in payload["teleportation"]
    assert "pass_profile" not in payload
    assert payload["schema_version"] == "2.0"
    assert payload["link"] == {
        "medium": "atmospheric",
        "topology": "point_to_point",
        "protocol": "decoy_bb84",
    }
    assert payload["profile"]["axis"]["name"] == "time_s"
    assert payload["mission"] == result.mission
    assert detect_results_schema(payload) == "2.0"
    assert validate_provenance(payload, payload["provenance"]) is True


def test_provenance_complete_for_summary_and_teleportation_fields():
    result = simulate_pass(MissionConfig(samples=11))
    summary_fields = {"headline_key_yield", "headline_fidelity"}
    teleportation_fields = {"frames", "average_fidelity", "classical_limit", "plot"}

    for field_name in summary_fields:
        assert f"summary.{field_name}" in result.provenance
    for field_name in teleportation_fields:
        assert f"teleportation.{field_name}" in result.provenance


def test_run_py_delegates_physics_to_mission_composition():
    source = Path("src/qkd/run.py").read_text(encoding="utf-8")

    assert "from qkd.mission import simulate_pass" in source
    assert "channel_state" not in source
    assert "satellite_pass" not in source
    assert "teleportation_fidelity" not in source
    assert "run_decoy_bb84" not in source
    assert "from qkd.coherence" not in source
    assert "effective_werner_p_for_sky(" not in source
    assert "log10" not in source


def test_signals_dataclasses_are_unchanged_by_mission_composition():
    assert [field.name for field in fields(ChannelState)] == [
        "transmittance",
        "werner_p",
        "intrinsic_qber",
        "dark_count_prob",
        "slant_range_km",
        "elevation_deg",
    ]
    assert [field.name for field in fields(PhysicsSignals)] == [
        "qber",
        "decoy_anomaly_score",
        "chsh_margin",
        "teleportation_margin",
        "loss_rate",
        "secure_key_rate",
    ]
