"""Shared Phase 2 interface dataclasses.

These contracts are defined in Phase 2A and populated by later phases.
They intentionally contain no trust or coherence fields.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChannelState:
    """Physical channel conditions resolved to the governing parameters."""

    transmittance: float
    werner_p: float
    intrinsic_qber: float
    dark_count_prob: float
    slant_range_km: float | None = None
    elevation_deg: float | None = None


@dataclass
class DetectorParams:
    """Receiver-side detector parameters."""

    detection_efficiency: float
    dark_count_prob: float
    error_correction_efficiency: float = 1.16


@dataclass
class PhysicsSignals:
    """Physics-only signals for later trust/coherence derivation."""

    qber: float
    decoy_anomaly_score: float
    chsh_margin: float
    teleportation_margin: float
    loss_rate: float
    secure_key_rate: float
