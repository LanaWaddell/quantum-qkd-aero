"""LINK-6a Gate B tests: replay manifest, effect registry, replay round-trip.

``docs/LINK_6A_PLAN.md`` v2.3.1 §4, Appendix A.2/A.2.1/A.2.2/A.5. Mission
integration (``simulate_pass`` activation rules) lives in
``tests/test_link6a.py``; this file is scoped to ``qkd.replay``.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from qkd.detection import PdtConfig, ReceiverModel
from qkd.effects import (
    AtmosphericAbsorptionEffect,
    BackgroundLightEffect,
    DetectorAfterpulsingEffect,
    DetectorDarkRateEffect,
    DetectorDeadTimeEffect,
    DetectorQuantumEfficiencyEffect,
    DopplerShiftEffect,
    GeometricLossEffect,
    MuFluctuationEffect,
    PointingJitterEffect,
    PointingLossEffect,
    ScintillationFadingEffect,
    SystemEfficiencyEffect,
)
from qkd.link import LinkObservables
from qkd.mission import MissionConfig, simulate_pass
from qkd.replay import (
    EFFECT_CODECS,
    LINK_PIPELINE_VERSION,
    ManifestValidationError,
    PRODUCTION_EFFECT_IDS,
    ReplayRefusedError,
    UnknownEffectTypeError,
    _validate_manifest_json,
    replay_from_provenance,
    validate_manifest_object,
)


def _valid_manifest_dict() -> dict:
    return {
        "manifest_version": 1,
        "replayability": "replayable",
        "mission_config": {
            "samples": 10,
            "altitude_km": 550.0,
            "peak_elevation_deg": 90.0,
            "horizon_elevation_deg": 10.0,
            "atmosphere": {
                "zenith_optical_depth": 0.2,
                "system_efficiency": 0.5,
                "beam_divergence_urad": 10.0,
                "rx_aperture_m": 0.5,
                "intrinsic_qber": 0.015,
                "dark_count_prob": 1e-6,
                "werner_p": 0.98,
            },
            "detector": {
                "detection_efficiency": 0.5,
                "dark_count_prob": 1e-6,
                "error_correction_efficiency": 1.16,
            },
            "intensities": {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0},
            "n_pulses": 1_000_000,
            "pulse_repetition_rate_hz": 1.0e8,
            "sky_condition": "night",
        },
        "production_effects": list(PRODUCTION_EFFECT_IDS),
        "effects": [],
        "link_seed": None,
        "link_controls": {},
        "mode": "sampled",
        "model_ids": {"receiver": None, "pdt": None},
        "pipeline_version": LINK_PIPELINE_VERSION,
        "schema_version": "2.0",
        "serialization": {
            "format": "canonical-json-v1",
            "sort_keys": True,
            "separators": [",", ":"],
            "ensure_ascii": True,
            "float_repr": "python-repr",
        },
    }


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# A.2.2 -- codec anti-drift test
# ---------------------------------------------------------------------------


def test_effect_codecs_cover_exactly_the_thirteen_registered_effect_ids():
    assert set(EFFECT_CODECS) == {
        "system_efficiency",
        "atmospheric_absorption",
        "geometric_loss",
        "detector_qe",
        "doppler_shift",
        "pointing_loss",
        "scintillation_fading",
        "pointing_jitter",
        "mu_fluctuation",
        "detector_afterpulsing",
        "detector_dead_time",
        "background_light",
        "detector_dark_rate",
    }


def test_effect_codec_param_keys_match_init_true_fields_minus_effect_id():
    for effect_id, codec in EFFECT_CODECS.items():
        init_fields = {
            f.name
            for f in dataclasses.fields(codec.cls)
            if f.init and f.name != "effect_id"
        }
        assert set(codec.param_keys) == init_fields, effect_id


def test_production_effects_order_is_pinned():
    assert PRODUCTION_EFFECT_IDS == (
        "system_efficiency",
        "atmospheric_absorption",
        "geometric_loss",
        "detector_qe",
    )


# ---------------------------------------------------------------------------
# §4 -- manifest closed-world validation (A.2, A.5)
# ---------------------------------------------------------------------------


def test_link_pipeline_version_constant_has_the_plan_frozen_value():
    assert LINK_PIPELINE_VERSION == "link-6a.1"


def test_valid_manifest_round_trips_through_validation():
    manifest = _valid_manifest_dict()
    validate_manifest_object(manifest)
    manifest_json = _canonical(manifest)
    _validate_manifest_json(manifest_json)  # no raise


def test_unknown_top_level_key_rejected():
    manifest = _valid_manifest_dict()
    manifest["unexpected_key"] = 1
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_missing_required_top_level_key_rejected():
    manifest = _valid_manifest_dict()
    del manifest["link_seed"]
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_unknown_key_inside_mission_config_rejected():
    manifest = _valid_manifest_dict()
    manifest["mission_config"]["extra"] = 1
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_unknown_key_inside_mission_config_atmosphere_rejected():
    manifest = _valid_manifest_dict()
    manifest["mission_config"]["atmosphere"]["extra"] = 1
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_unknown_key_inside_mission_config_detector_rejected():
    manifest = _valid_manifest_dict()
    manifest["mission_config"]["detector"]["extra"] = 1
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_sky_condition_outside_enum_rejected():
    manifest = _valid_manifest_dict()
    manifest["mission_config"]["sky_condition"] = "midnight"
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_unknown_key_inside_receiver_rejected():
    manifest = _valid_manifest_dict()
    manifest["receiver"] = {"pi": {"signal": 0.8, "decoy": 0.15, "vacuum": 0.05}, "operating_convention": "next_live_gate_v1"}
    manifest["model_ids"]["receiver"] = "qkd_receiver_mean_field_v1"
    manifest["receiver"]["extra"] = 1
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_receiver_object_containing_calibrated_pair_fields_rejected():
    # F2: the calibrated (p_ap, dead_time_s) pair is not duplicated in
    # 'receiver' -- single ownership stays with the ordered effect specs.
    manifest = _valid_manifest_dict()
    manifest["receiver"] = {
        "pi": {"signal": 0.8, "decoy": 0.15, "vacuum": 0.05},
        "operating_convention": "next_live_gate_v1",
        "afterpulse_prob": 0.02,
    }
    manifest["model_ids"]["receiver"] = "qkd_receiver_mean_field_v1"
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_unknown_key_inside_pdt_config_rejected():
    manifest = _valid_manifest_dict()
    manifest["mode"] = "pdt"
    manifest["model_ids"]["pdt"] = "pdt_gauss_hermite_21_v1"
    manifest["pdt_config"] = {
        "fading_coherence_time_s": 3e-3,
        "block_duration_s": 0.476955506437,
        "tau_mem_s": 1.01e-6,
        "order": "conditional_then_average",
        "extra": 1,
    }
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_unknown_key_inside_model_ids_rejected():
    manifest = _valid_manifest_dict()
    manifest["model_ids"]["extra"] = None
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_unknown_key_inside_serialization_rejected():
    manifest = _valid_manifest_dict()
    manifest["serialization"]["extra"] = 1
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_unknown_key_inside_registered_effect_params_rejected():
    manifest = _valid_manifest_dict()
    manifest["effects"] = [
        {
            "effect_id": "detector_dead_time",
            "type_id": EFFECT_CODECS["detector_dead_time"].type_id,
            "parameters_complete": True,
            "params": {"dead_time_s": 1e-6, "extra": 1},
        }
    ]
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_serialization_rules_must_equal_the_frozen_contract():
    manifest = _valid_manifest_dict()
    manifest["serialization"]["sort_keys"] = False
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_canonical_json_reserialization_mismatch_rejected():
    manifest = _valid_manifest_dict()
    manifest_json = _canonical(manifest)
    # A byte that makes the parsed form re-serialize differently: extra
    # whitespace (still valid JSON, but not canonical form).
    tampered = manifest_json.replace('"manifest_version":1', '"manifest_version": 1')
    with pytest.raises(ManifestValidationError):
        _validate_manifest_json(tampered)


def test_link_seed_non_int_rejected():
    manifest = _valid_manifest_dict()
    manifest["link_seed"] = 1.5
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_manifest_version_unsupported_rejected():
    manifest = _valid_manifest_dict()
    manifest["manifest_version"] = 2
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_non_finite_numeric_leaf_rejected():
    manifest = _valid_manifest_dict()
    manifest["mission_config"]["altitude_km"] = float("nan")
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_replayability_enum_vocabulary_rejected():
    manifest = _valid_manifest_dict()
    manifest["replayability"] = "sort_of_replayable"
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_mode_enum_vocabulary_rejected():
    manifest = _valid_manifest_dict()
    manifest["mode"] = "hybrid"
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_pdt_order_enum_vocabulary_rejected():
    manifest = _valid_manifest_dict()
    manifest["mode"] = "pdt"
    manifest["model_ids"]["pdt"] = "pdt_gauss_hermite_21_v1"
    manifest["pdt_config"] = {
        "fading_coherence_time_s": 3e-3,
        "block_duration_s": 0.476955506437,
        "tau_mem_s": 1.01e-6,
        "order": "average_then_conditional",
    }
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_unknown_effect_type_on_replay_rejected():
    manifest = _valid_manifest_dict()
    manifest["effects"] = [
        {
            "effect_id": "not_a_real_effect",
            "type_id": "qkd.effects.NotARealEffect",
            "parameters_complete": True,
            "params": {},
        }
    ]
    manifest_json = _canonical(manifest)
    with pytest.raises(ManifestValidationError):
        # effect_id not in EFFECT_CODECS but params key set can't be
        # checked -- still validates the envelope; replay itself raises
        # UnknownEffectTypeError for the reconstruction step.
        _validate_manifest_json(manifest_json)


def test_replay_refuses_configuration_auditable_manifest():
    manifest = _valid_manifest_dict()
    manifest["replayability"] = "configuration_auditable"
    manifest["effects"] = [
        {
            "effect_id": "custom_thing",
            "type_id": "tests.test_replay.CustomEffect",
            "parameters_complete": False,
            "params": {},
        }
    ]
    manifest_json = _canonical(manifest)
    with pytest.raises(ReplayRefusedError):
        replay_from_provenance(manifest_json)


# ---------------------------------------------------------------------------
# §4 -- production replay entry point: real round trip through simulate_pass
# ---------------------------------------------------------------------------


def test_replay_from_provenance_is_byte_identical_in_process():
    receiver = ReceiverModel(pi=(0.8, 0.15, 0.05))
    result = simulate_pass(MissionConfig(samples=25), receiver=receiver)
    assert result.link_provenance is not None

    replayed = replay_from_provenance(result.link_provenance)

    assert dataclasses.asdict(replayed) == dataclasses.asdict(result)


def test_replay_from_provenance_with_registered_effects_round_trips():
    receiver = ReceiverModel(pi=(0.8, 0.15, 0.05))
    result = simulate_pass(
        MissionConfig(samples=15),
        receiver=receiver,
        link_effects=[
            BackgroundLightEffect(background_rate_hz=1.0e5),
            DetectorAfterpulsingEffect(afterpulse_prob=0.01),
        ],
        link_controls={"gate_window_s": 1e-9},
    )
    replayed = replay_from_provenance(result.link_provenance)
    assert dataclasses.asdict(replayed) == dataclasses.asdict(result)


def test_replay_from_provenance_pdt_round_trips():
    receiver = ReceiverModel(pi=(0.8, 0.15, 0.05))
    pdt_config = PdtConfig(fading_coherence_time_s=3e-3, block_duration_s=0.476955506437)
    result = simulate_pass(
        MissionConfig(),
        receiver=receiver,
        link_effects=[ScintillationFadingEffect(rytov_variance_zenith=0.02, aperture_averaging=0.5)],
        link_mode="pdt",
        pdt_config=pdt_config,
    )
    replayed = replay_from_provenance(result.link_provenance)
    assert dataclasses.asdict(replayed) == dataclasses.asdict(result)


def test_manifest_replayability_is_replayable_when_all_effects_registered():
    receiver = ReceiverModel(pi=(0.8, 0.15, 0.05))
    result = simulate_pass(
        MissionConfig(samples=10),
        receiver=receiver,
        link_effects=[DopplerShiftEffect(carrier_frequency_hz=3.8e14)]
        if False
        else [PointingLossEffect(boresight_offset_urad=1.0, beam_divergence_urad=10.0)],
    )
    manifest = json.loads(result.link_provenance)
    assert manifest["replayability"] == "replayable"


def test_manifest_replayability_is_configuration_auditable_for_unregistered_effect():
    from dataclasses import dataclass, field

    @dataclass(frozen=True)
    class _CustomEffect:
        effect_id: str = field(default="custom_thing", init=False)

        def evaluate(self, t, geom, *, context):
            return LinkObservables()

    receiver = ReceiverModel(pi=(0.8, 0.15, 0.05))
    result = simulate_pass(
        MissionConfig(samples=10), receiver=receiver, link_effects=[_CustomEffect()]
    )
    manifest = json.loads(result.link_provenance)
    assert manifest["replayability"] == "configuration_auditable"
    assert manifest["effects"][0]["parameters_complete"] is False
    assert manifest["effects"][0]["params"] == {}
    with pytest.raises(ReplayRefusedError):
        replay_from_provenance(result.link_provenance)


def test_custom_effect_with_audit_spec_is_replayable_with_complete_parameters():
    from dataclasses import dataclass, field

    @dataclass(frozen=True)
    class _AuditableEffect:
        magnitude: float
        effect_id: str = field(default="auditable_thing", init=False)

        def evaluate(self, t, geom, *, context):
            return LinkObservables()

        def audit_spec(self):
            return {"magnitude": self.magnitude}

    receiver = ReceiverModel(pi=(0.8, 0.15, 0.05))
    result = simulate_pass(
        MissionConfig(samples=10), receiver=receiver, link_effects=[_AuditableEffect(magnitude=3.5)]
    )
    manifest = json.loads(result.link_provenance)
    assert manifest["effects"][0]["parameters_complete"] is True
    assert manifest["effects"][0]["params"] == {"magnitude": 3.5}
    # Still "configuration_auditable" (unregistered type) -- audit_spec
    # completeness does not itself make the type replayable.
    assert manifest["replayability"] == "configuration_auditable"


def test_audit_spec_non_scalar_value_rejected():
    from dataclasses import dataclass, field

    from qkd.replay import AuditSpecValidationError

    @dataclass(frozen=True)
    class _BadAuditEffect:
        effect_id: str = field(default="bad_audit_thing", init=False)

        def evaluate(self, t, geom, *, context):
            return LinkObservables()

        def audit_spec(self):
            return {"bad": [1, 2, 3]}

    receiver = ReceiverModel(pi=(0.8, 0.15, 0.05))
    with pytest.raises(AuditSpecValidationError):
        simulate_pass(MissionConfig(samples=10), receiver=receiver, link_effects=[_BadAuditEffect()])
