"""Eavesdropper strategies for Phase 2B decoy-state BB84."""

from __future__ import annotations

import math


class EveStrategy:
    """Base class for per-photon-number Eve behavior."""

    name = "base"

    def signal_detection_probability(
        self,
        photon_number,
        *,
        eta,
        intensity,
        signal_intensity,
        target_signal_gain,
        dark_count_prob,
    ):
        raise NotImplementedError

    def signal_error_rate(self, photon_number, *, intrinsic_qber):
        return intrinsic_qber


class NullEve(EveStrategy):
    """No-op Eve; preserves the honest channel through the Eve pipeline."""

    name = "null"

    def signal_detection_probability(
        self,
        photon_number,
        *,
        eta,
        intensity,
        signal_intensity,
        target_signal_gain,
        dark_count_prob,
    ):
        _validate_photon_number(photon_number)
        return 1.0 - ((1.0 - eta) ** photon_number)


class InterceptResend(NullEve):
    """Simplified loud-adversary contrast model.

    It preserves honest gains and applies the canonical ~25% BB84
    intercept-resend error signature, but is not a full photon-number/loss-aware
    intercept-resend hardware model.
    """

    name = "intercept_resend"

    def signal_error_rate(self, photon_number, *, intrinsic_qber):
        _validate_photon_number(photon_number)
        return 0.25


class QND_PNS(EveStrategy):
    """QND photon-number splitting attack.

    The attack favors multi-photon pulses without adding polarization
    disturbance: zero-photon pulses have no signal photon, single-photon pulses
    are forwarded only by a computed fraction, and multi-photon pulses are
    forwarded through Eve's lossless line after she keeps one photon.
    """

    name = "qnd_pns"

    def __init__(self, single_photon_forwarding_fraction=None):
        if single_photon_forwarding_fraction is not None:
            _validate_probability(single_photon_forwarding_fraction)
        self.single_photon_forwarding_fraction = single_photon_forwarding_fraction

    def signal_detection_probability(
        self,
        photon_number,
        *,
        eta,
        intensity,
        signal_intensity,
        target_signal_gain,
        dark_count_prob,
    ):
        _validate_photon_number(photon_number)

        if photon_number == 0:
            return 0.0
        if photon_number == 1:
            return self._single_photon_forwarding_fraction(
                signal_intensity=signal_intensity,
                target_signal_gain=target_signal_gain,
                dark_count_prob=dark_count_prob,
            )
        return 1.0

    def _single_photon_forwarding_fraction(
        self,
        *,
        signal_intensity,
        target_signal_gain,
        dark_count_prob,
    ):
        if self.single_photon_forwarding_fraction is not None:
            return self.single_photon_forwarding_fraction

        if signal_intensity <= 0.0:
            raise ValueError("signal_intensity must be positive.")
        if not 0.0 <= target_signal_gain <= 1.0:
            raise ValueError("target_signal_gain must be in [0, 1].")
        if not 0.0 <= dark_count_prob < 1.0:
            raise ValueError("dark_count_prob must be in [0, 1).")

        p0 = math.exp(-signal_intensity)
        p1 = signal_intensity * p0
        no_signal_target = (1.0 - target_signal_gain) / (1.0 - dark_count_prob)
        forwarding_fraction = 1.0 - ((no_signal_target - p0) / p1)

        if not 0.0 <= forwarding_fraction <= 1.0:
            raise ValueError(
                "QND_PNS cannot match the target signal gain with a physical "
                "single-photon forwarding fraction."
            )

        return forwarding_fraction


def _validate_photon_number(photon_number):
    if photon_number < 0:
        raise ValueError("photon_number must be non-negative.")


def _validate_probability(value):
    if not 0.0 <= value <= 1.0:
        raise ValueError("probability must be in [0, 1].")
