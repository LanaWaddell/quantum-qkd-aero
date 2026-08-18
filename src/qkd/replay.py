"""LINK-6a: versioned replay manifest, effect registry, and production replay entry point.

Implements ``docs/LINK_6A_PLAN.md`` §4 and Appendix A.2. ``run_metadata.link_provenance``
is a canonical-JSON **string** (sorted keys, declared separators) containing this
manifest. ``replay_from_provenance`` reconstructs a ``PassResult`` through the
**real** ``qkd.mission.simulate_pass`` path -- it never half-replays or hand-rebuilds
intermediate state.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real

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
from qkd.link import ChannelEffect
from qkd.signals import DetectorParams


LINK_PIPELINE_VERSION = "link-6a.1"
RESULTS_SCHEMA_VERSION = "2.0"

PRODUCTION_EFFECT_IDS = (
    "system_efficiency",
    "atmospheric_absorption",
    "geometric_loss",
    "detector_qe",
)


class ReplayError(ValueError):
    """Base class for replay/manifest binding-rule violations."""


class ManifestValidationError(ReplayError):
    """Raised when a parsed manifest violates the closed-world A.2 schema."""


class UnknownEffectTypeError(ReplayError):
    """Raised by :func:`replay_from_provenance` for an unregistered/mismatched effect type."""


class ReplayRefusedError(ReplayError):
    """Raised when a ``"configuration_auditable"`` manifest is submitted for replay."""


class AuditSpecValidationError(ReplayError):
    """Raised when a custom effect's ``audit_spec()`` returns a non-scalar/non-finite value."""


# ---------------------------------------------------------------------------
# Effect registry (A.2.2 -- codec-owned param_keys, to_spec/from_spec)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectCodec:
    effect_id: str
    type_id: str
    param_keys: tuple[str, ...]
    cls: type

    def to_spec(self, effect: ChannelEffect) -> dict[str, object]:
        return {key: getattr(effect, key) for key in self.param_keys}

    def from_spec(self, params: Mapping[str, object]) -> ChannelEffect:
        return self.cls(**{key: params[key] for key in self.param_keys})


def _type_id(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


_EFFECT_REGISTRY: tuple[tuple[str, type, tuple[str, ...]], ...] = (
    ("system_efficiency", SystemEfficiencyEffect, ("system_efficiency",)),
    ("atmospheric_absorption", AtmosphericAbsorptionEffect, ("zenith_optical_depth",)),
    ("geometric_loss", GeometricLossEffect, ("beam_divergence_urad", "rx_aperture_m")),
    ("detector_qe", DetectorQuantumEfficiencyEffect, ("detection_efficiency",)),
    ("doppler_shift", DopplerShiftEffect, ("carrier_frequency_hz",)),
    ("pointing_loss", PointingLossEffect, ("boresight_offset_urad", "beam_divergence_urad")),
    (
        "scintillation_fading",
        ScintillationFadingEffect,
        ("rytov_variance_zenith", "aperture_averaging", "allow_out_of_regime"),
    ),
    ("pointing_jitter", PointingJitterEffect, ("jitter_sigma_urad", "beam_divergence_urad")),
    ("mu_fluctuation", MuFluctuationEffect, ("relative_sigma",)),
    ("detector_afterpulsing", DetectorAfterpulsingEffect, ("afterpulse_prob",)),
    ("detector_dead_time", DetectorDeadTimeEffect, ("dead_time_s",)),
    ("background_light", BackgroundLightEffect, ("background_rate_hz",)),
    ("detector_dark_rate", DetectorDarkRateEffect, ("dark_count_rate_hz",)),
)

EFFECT_CODECS: dict[str, EffectCodec] = {
    effect_id: EffectCodec(
        effect_id=effect_id, type_id=_type_id(cls), param_keys=param_keys, cls=cls
    )
    for effect_id, cls, param_keys in _EFFECT_REGISTRY
}

_CODEC_BY_CLASS: dict[type, EffectCodec] = {codec.cls: codec for codec in EFFECT_CODECS.values()}


# ---------------------------------------------------------------------------
# Canonical JSON (A.2 serialization rules)
# ---------------------------------------------------------------------------

_SERIALIZATION_RULES = {
    "format": "canonical-json-v1",
    "sort_keys": True,
    "separators": [",", ":"],
    "ensure_ascii": True,
    "float_repr": "python-repr",
}


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _validate_audit_params(params: Mapping[str, object], effect_id: str) -> None:
    if not isinstance(params, Mapping):
        raise AuditSpecValidationError(
            f"audit_spec() for effect_id={effect_id!r} must return a Mapping."
        )
    for key, value in params.items():
        if not isinstance(key, str):
            raise AuditSpecValidationError(
                f"audit_spec() for effect_id={effect_id!r} returned a non-string key {key!r}."
            )
        if isinstance(value, bool) or value is None or isinstance(value, str):
            continue
        if isinstance(value, Real):
            if not math.isfinite(float(value)):
                raise AuditSpecValidationError(
                    f"audit_spec() for effect_id={effect_id!r} key {key!r} is non-finite."
                )
            continue
        raise AuditSpecValidationError(
            f"audit_spec() for effect_id={effect_id!r} key {key!r} has non-scalar value "
            f"{value!r}; only JSON scalars (float, int, str, bool, None) are permitted."
        )


# ---------------------------------------------------------------------------
# §4 -- manifest construction
# ---------------------------------------------------------------------------


def build_manifest(
    *,
    mission_config: object,
    resolved_atmosphere: Mapping[str, object],
    link_effects: Sequence[ChannelEffect],
    link_seed: int | None,
    link_controls: Mapping[str, float] | None,
    receiver: ReceiverModel | None,
    link_mode: str,
    pdt_config: PdtConfig | None,
    tau_mem_s: float | None,
) -> str:
    """Build the canonical-JSON manifest string (plan §4, Appendix A.2)."""

    effects_specs: list[dict[str, object]] = []
    replayable = True
    for effect in link_effects:
        codec = _CODEC_BY_CLASS.get(type(effect))
        type_id = codec.type_id if codec is not None else _type_id(type(effect))
        if codec is not None:
            effects_specs.append(
                {
                    "effect_id": effect.effect_id,
                    "type_id": type_id,
                    "parameters_complete": True,
                    "params": codec.to_spec(effect),
                }
            )
            continue

        # Unregistered effect type: no ``from_spec`` exists for it, so this
        # manifest can never be replayed regardless of parameter
        # completeness (plan §4, C5) -- "configuration_auditable" either way.
        replayable = False
        audit_spec = getattr(effect, "audit_spec", None)
        if callable(audit_spec):
            params = audit_spec()
            _validate_audit_params(params, effect.effect_id)
            effects_specs.append(
                {
                    "effect_id": effect.effect_id,
                    "type_id": type_id,
                    "parameters_complete": True,
                    "params": dict(params),
                }
            )
        else:
            effects_specs.append(
                {
                    "effect_id": effect.effect_id,
                    "type_id": type_id,
                    "parameters_complete": False,
                    "params": {},
                }
            )

    detector: DetectorParams = mission_config.detector
    mission_config_obj = {
        "samples": mission_config.samples,
        "altitude_km": mission_config.altitude_km,
        "peak_elevation_deg": mission_config.peak_elevation_deg,
        "horizon_elevation_deg": mission_config.horizon_elevation_deg,
        "atmosphere": dict(resolved_atmosphere),
        "detector": {
            "detection_efficiency": detector.detection_efficiency,
            "dark_count_prob": detector.dark_count_prob,
            "error_correction_efficiency": detector.error_correction_efficiency,
        },
        "intensities": dict(mission_config.intensities),
        "n_pulses": mission_config.n_pulses,
        "pulse_repetition_rate_hz": mission_config.pulse_repetition_rate_hz,
        "sky_condition": mission_config.sky_condition,
    }

    manifest: dict[str, object] = {
        "manifest_version": 1,
        "replayability": "replayable" if replayable else "configuration_auditable",
        "mission_config": mission_config_obj,
        "production_effects": list(PRODUCTION_EFFECT_IDS),
        "effects": effects_specs,
        "link_seed": link_seed,
        "link_controls": dict(link_controls) if link_controls else {},
        "mode": link_mode,
        "model_ids": {
            "receiver": "qkd_receiver_mean_field_v1" if receiver is not None else None,
            "pdt": "pdt_gauss_hermite_21_v1" if link_mode == "pdt" else None,
        },
        "pipeline_version": LINK_PIPELINE_VERSION,
        "schema_version": RESULTS_SCHEMA_VERSION,
        "serialization": dict(_SERIALIZATION_RULES),
    }
    if receiver is not None:
        manifest["receiver"] = {
            "pi": {
                "signal": receiver.pi[0],
                "decoy": receiver.pi[1],
                "vacuum": receiver.pi[2],
            },
            "operating_convention": receiver.operating_convention,
        }
    if link_mode == "pdt":
        manifest["pdt_config"] = {
            "fading_coherence_time_s": pdt_config.fading_coherence_time_s,
            "block_duration_s": pdt_config.block_duration_s,
            "tau_mem_s": tau_mem_s,
            "order": "conditional_then_average",
        }

    return _canonical_json(manifest)


# ---------------------------------------------------------------------------
# A.2 closed-world manifest validation
# ---------------------------------------------------------------------------

_MISSION_CONFIG_KEYS = frozenset(
    {
        "samples",
        "altitude_km",
        "peak_elevation_deg",
        "horizon_elevation_deg",
        "atmosphere",
        "detector",
        "intensities",
        "n_pulses",
        "pulse_repetition_rate_hz",
        "sky_condition",
    }
)
_ATMOSPHERE_KEYS = frozenset(
    {
        "zenith_optical_depth",
        "system_efficiency",
        "beam_divergence_urad",
        "rx_aperture_m",
        "intrinsic_qber",
        "dark_count_prob",
        "werner_p",
    }
)
_DETECTOR_KEYS = frozenset(
    {"detection_efficiency", "dark_count_prob", "error_correction_efficiency"}
)
_INTENSITY_KEYS = frozenset({"signal", "decoy", "vacuum"})
_SKY_CONDITIONS = frozenset({"night", "twilight", "day"})
_RECEIVER_KEYS = frozenset({"pi", "operating_convention"})
_PI_KEYS = frozenset({"signal", "decoy", "vacuum"})
_PDT_CONFIG_KEYS = frozenset(
    {"fading_coherence_time_s", "block_duration_s", "tau_mem_s", "order"}
)
_MODEL_IDS_KEYS = frozenset({"receiver", "pdt"})
_SERIALIZATION_KEYS = frozenset(_SERIALIZATION_RULES)
_EFFECT_SPEC_KEYS = frozenset({"effect_id", "type_id", "parameters_complete", "params"})
_TOP_LEVEL_REQUIRED_KEYS = frozenset(
    {
        "manifest_version",
        "replayability",
        "mission_config",
        "production_effects",
        "effects",
        "link_seed",
        "link_controls",
        "mode",
        "model_ids",
        "pipeline_version",
        "schema_version",
        "serialization",
    }
)
_TOP_LEVEL_ALLOWED_KEYS = _TOP_LEVEL_REQUIRED_KEYS | {"receiver", "pdt_config"}
_REPLAYABILITY_VALUES = frozenset({"replayable", "configuration_auditable"})
_MODE_VALUES = frozenset({"sampled", "pdt"})
_ORDER_VALUES = frozenset({"conditional_then_average"})
_RECEIVER_MODEL_IDS = frozenset({"qkd_receiver_mean_field_v1"})
_PDT_MODEL_IDS = frozenset({"pdt_gauss_hermite_21_v1"})


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ManifestValidationError(f"{path} must be an object.")
    return value


def _require_closed_keys(value: Mapping[str, object], allowed: frozenset[str], path: str) -> None:
    extra = set(value) - allowed
    if extra:
        raise ManifestValidationError(
            f"{path} has unknown key(s): {sorted(extra)}; allowed: {sorted(allowed)}."
        )


def _require_exact_keys(value: Mapping[str, object], required: frozenset[str], path: str) -> None:
    _require_closed_keys(value, required, path)
    missing = required - set(value)
    if missing:
        raise ManifestValidationError(f"{path} is missing required key(s): {sorted(missing)}.")


def _require_finite_number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ManifestValidationError(f"{path} must be a finite number.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ManifestValidationError(f"{path} must be finite.")
    return numeric


def _require_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestValidationError(f"{path} must be an integer.")
    return value


def _require_str(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise ManifestValidationError(f"{path} must be a string.")
    return value


def _require_member(value: str, allowed: frozenset[str], path: str) -> None:
    if value not in allowed:
        raise ManifestValidationError(f"{path} must be one of {sorted(allowed)}; got {value!r}.")


def validate_manifest_object(manifest: Mapping[str, object]) -> None:
    """Deep closed-world validation of a *parsed* manifest object (plan §4, Appendix A.2/A.5)."""

    if not isinstance(manifest, Mapping):
        raise ManifestValidationError("Manifest must be a JSON object.")
    _require_closed_keys(manifest, _TOP_LEVEL_ALLOWED_KEYS, "")
    missing = _TOP_LEVEL_REQUIRED_KEYS - set(manifest)
    if missing:
        raise ManifestValidationError(f"Manifest is missing required key(s): {sorted(missing)}.")

    if manifest["manifest_version"] != 1:
        raise ManifestValidationError(
            f"manifest_version must be 1; got {manifest['manifest_version']!r}."
        )
    replayability = _require_str(manifest["replayability"], "replayability")
    _require_member(replayability, _REPLAYABILITY_VALUES, "replayability")

    mission_config = _require_mapping(manifest["mission_config"], "mission_config")
    _require_exact_keys(mission_config, _MISSION_CONFIG_KEYS, "mission_config")
    _require_int(mission_config["samples"], "mission_config.samples")
    if mission_config["samples"] <= 0:
        raise ManifestValidationError("mission_config.samples must be > 0.")
    for key in ("altitude_km", "peak_elevation_deg", "horizon_elevation_deg"):
        _require_finite_number(mission_config[key], f"mission_config.{key}")
    atmosphere = _require_mapping(mission_config["atmosphere"], "mission_config.atmosphere")
    _require_exact_keys(atmosphere, _ATMOSPHERE_KEYS, "mission_config.atmosphere")
    for key in _ATMOSPHERE_KEYS:
        _require_finite_number(atmosphere[key], f"mission_config.atmosphere.{key}")
    detector = _require_mapping(mission_config["detector"], "mission_config.detector")
    _require_exact_keys(detector, _DETECTOR_KEYS, "mission_config.detector")
    for key in _DETECTOR_KEYS:
        _require_finite_number(detector[key], f"mission_config.detector.{key}")
    intensities = _require_mapping(mission_config["intensities"], "mission_config.intensities")
    _require_exact_keys(intensities, _INTENSITY_KEYS, "mission_config.intensities")
    for key in _INTENSITY_KEYS:
        _require_finite_number(intensities[key], f"mission_config.intensities.{key}")
    _require_int(mission_config["n_pulses"], "mission_config.n_pulses")
    _require_finite_number(
        mission_config["pulse_repetition_rate_hz"], "mission_config.pulse_repetition_rate_hz"
    )
    sky_condition = _require_str(mission_config["sky_condition"], "mission_config.sky_condition")
    _require_member(sky_condition, _SKY_CONDITIONS, "mission_config.sky_condition")

    production_effects = manifest["production_effects"]
    if not isinstance(production_effects, list) or any(
        not isinstance(item, str) for item in production_effects
    ):
        raise ManifestValidationError("production_effects must be an array of strings.")
    if tuple(production_effects) != PRODUCTION_EFFECT_IDS:
        raise ManifestValidationError(
            f"production_effects must equal {list(PRODUCTION_EFFECT_IDS)} in order; "
            f"got {production_effects!r}."
        )

    effects = manifest["effects"]
    if not isinstance(effects, list):
        raise ManifestValidationError("effects must be an array.")
    for index, spec in enumerate(effects):
        path = f"effects[{index}]"
        spec_map = _require_mapping(spec, path)
        _require_exact_keys(spec_map, _EFFECT_SPEC_KEYS, path)
        effect_id = _require_str(spec_map["effect_id"], f"{path}.effect_id")
        _require_str(spec_map["type_id"], f"{path}.type_id")
        if not isinstance(spec_map["parameters_complete"], bool):
            raise ManifestValidationError(f"{path}.parameters_complete must be a bool.")
        params = _require_mapping(spec_map["params"], f"{path}.params")
        codec = EFFECT_CODECS.get(effect_id)
        if codec is not None and spec_map["type_id"] == codec.type_id:
            _require_exact_keys(params, frozenset(codec.param_keys), f"{path}.params")

    all_registered = all(
        (codec := EFFECT_CODECS.get(spec["effect_id"])) is not None
        and spec["type_id"] == codec.type_id
        for spec in effects
    )
    expected_replayability = "replayable" if all_registered else "configuration_auditable"
    if replayability != expected_replayability:
        raise ManifestValidationError(
            f"replayability={replayability!r} is inconsistent with the effects array "
            f"(expected {expected_replayability!r}: every effect codec-registered "
            "with a matching type_id iff 'replayable')."
        )

    link_seed = manifest["link_seed"]
    if link_seed is not None and (isinstance(link_seed, bool) or not isinstance(link_seed, int)):
        raise ManifestValidationError("link_seed must be an int or null.")

    link_controls = _require_mapping(manifest["link_controls"], "link_controls")
    for key, value in link_controls.items():
        _require_finite_number(value, f"link_controls.{key}")

    mode = _require_str(manifest["mode"], "mode")
    _require_member(mode, _MODE_VALUES, "mode")

    if "receiver" in manifest:
        receiver = _require_mapping(manifest["receiver"], "receiver")
        _require_exact_keys(receiver, _RECEIVER_KEYS, "receiver")
        pi = _require_mapping(receiver["pi"], "receiver.pi")
        _require_exact_keys(pi, _PI_KEYS, "receiver.pi")
        total = 0.0
        for key in _PI_KEYS:
            value = _require_finite_number(pi[key], f"receiver.pi.{key}")
            if value <= 0.0:
                raise ManifestValidationError(f"receiver.pi.{key} must be > 0.")
            total += value
        from qkd.detection import PI_SUM_TOLERANCE

        if abs(total - 1.0) > PI_SUM_TOLERANCE:
            raise ManifestValidationError(
                f"receiver.pi must sum to 1 within PI_SUM_TOLERANCE; got {total!r}."
            )
        operating_convention = _require_str(
            receiver["operating_convention"], "receiver.operating_convention"
        )
        _require_member(
            operating_convention, frozenset({"next_live_gate_v1"}), "receiver.operating_convention"
        )

    if mode == "pdt":
        if "pdt_config" not in manifest:
            raise ManifestValidationError("pdt_config is required when mode == 'pdt'.")
        pdt_config = _require_mapping(manifest["pdt_config"], "pdt_config")
        _require_exact_keys(pdt_config, _PDT_CONFIG_KEYS, "pdt_config")
        _require_finite_number(
            pdt_config["fading_coherence_time_s"], "pdt_config.fading_coherence_time_s"
        )
        _require_finite_number(pdt_config["block_duration_s"], "pdt_config.block_duration_s")
        _require_finite_number(pdt_config["tau_mem_s"], "pdt_config.tau_mem_s")
        order = _require_str(pdt_config["order"], "pdt_config.order")
        _require_member(order, _ORDER_VALUES, "pdt_config.order")
    elif "pdt_config" in manifest:
        raise ManifestValidationError("pdt_config must be absent when mode != 'pdt'.")

    model_ids = _require_mapping(manifest["model_ids"], "model_ids")
    _require_exact_keys(model_ids, _MODEL_IDS_KEYS, "model_ids")
    receiver_model_id = model_ids["receiver"]
    if receiver_model_id is not None:
        _require_str(receiver_model_id, "model_ids.receiver")
        _require_member(receiver_model_id, _RECEIVER_MODEL_IDS, "model_ids.receiver")
    if ("receiver" in manifest) != (receiver_model_id is not None):
        raise ManifestValidationError(
            "model_ids.receiver must be non-null iff the 'receiver' object is present."
        )
    pdt_model_id = model_ids["pdt"]
    if pdt_model_id is not None:
        _require_str(pdt_model_id, "model_ids.pdt")
        _require_member(pdt_model_id, _PDT_MODEL_IDS, "model_ids.pdt")
    if (mode == "pdt") != (pdt_model_id is not None):
        raise ManifestValidationError("model_ids.pdt must be non-null iff mode == 'pdt'.")

    _require_str(manifest["pipeline_version"], "pipeline_version")
    _require_str(manifest["schema_version"], "schema_version")

    serialization = _require_mapping(manifest["serialization"], "serialization")
    _require_exact_keys(serialization, _SERIALIZATION_KEYS, "serialization")
    if dict(serialization) != _SERIALIZATION_RULES:
        raise ManifestValidationError(
            f"serialization must equal {_SERIALIZATION_RULES!r}; got {dict(serialization)!r}."
        )


def _validate_manifest_json(manifest_json: str) -> dict[str, object]:
    if not isinstance(manifest_json, str):
        raise ManifestValidationError("Manifest must be a JSON string.")
    try:
        manifest = json.loads(manifest_json)
    except json.JSONDecodeError as exc:
        raise ManifestValidationError(f"Manifest is not valid JSON: {exc}") from exc
    validate_manifest_object(manifest)
    reserialized = _canonical_json(manifest)
    if reserialized != manifest_json:
        raise ManifestValidationError(
            "Manifest string does not equal its own canonical re-serialization "
            "(plan §4 serialization contract; canonical-JSON form)."
        )
    return manifest


# ---------------------------------------------------------------------------
# §4 -- production replay entry point
# ---------------------------------------------------------------------------


def replay_from_provenance(manifest_json: str):
    """Reconstruct and re-run a ``PassResult`` from a manifest string (plan §4).

    Rejects unknown effect types and unknown fields; refuses
    ``"configuration_auditable"`` manifests (it never half-replays). Routes
    through the real ``qkd.mission.simulate_pass`` -- never reconstructs
    intermediate stack state by hand.
    """

    manifest = _validate_manifest_json(manifest_json)

    if manifest["replayability"] != "replayable":
        raise ReplayRefusedError(
            f"Manifest replayability={manifest['replayability']!r}; replay is refused "
            "(plan §4, R7 -- it never half-replays)."
        )

    from qkd.mission import MissionConfig, simulate_pass  # deferred: avoid import cycle

    mission_config_obj = manifest["mission_config"]
    detector = DetectorParams(**mission_config_obj["detector"])
    config = MissionConfig(
        samples=mission_config_obj["samples"],
        altitude_km=mission_config_obj["altitude_km"],
        peak_elevation_deg=mission_config_obj["peak_elevation_deg"],
        horizon_elevation_deg=mission_config_obj["horizon_elevation_deg"],
        atmosphere=dict(mission_config_obj["atmosphere"]),
        detector=detector,
        intensities=dict(mission_config_obj["intensities"]),
        n_pulses=mission_config_obj["n_pulses"],
        pulse_repetition_rate_hz=mission_config_obj["pulse_repetition_rate_hz"],
        sky_condition=mission_config_obj["sky_condition"],
    )

    link_effects: list[ChannelEffect] = []
    for spec in manifest["effects"]:
        codec = EFFECT_CODECS.get(spec["effect_id"])
        if codec is None or codec.type_id != spec["type_id"]:
            raise UnknownEffectTypeError(
                f"Unknown or type-mismatched effect in manifest: {spec!r}."
            )
        link_effects.append(codec.from_spec(spec["params"]))

    receiver = None
    if "receiver" in manifest:
        receiver_obj = manifest["receiver"]
        pi_obj = receiver_obj["pi"]
        receiver = ReceiverModel(
            pi=(pi_obj["signal"], pi_obj["decoy"], pi_obj["vacuum"]),
            operating_convention=receiver_obj["operating_convention"],
        )

    pdt_config = None
    mode = manifest["mode"]
    if mode == "pdt":
        pdt_obj = manifest["pdt_config"]
        pdt_config = PdtConfig(
            fading_coherence_time_s=pdt_obj["fading_coherence_time_s"],
            block_duration_s=pdt_obj["block_duration_s"],
        )

    return simulate_pass(
        config,
        link_effects=link_effects,
        link_seed=manifest["link_seed"],
        link_controls=dict(manifest["link_controls"]),
        receiver=receiver,
        link_mode=mode,
        pdt_config=pdt_config,
    )
