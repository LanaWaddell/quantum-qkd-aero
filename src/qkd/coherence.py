"""Background-light degradation of the entangled-resource quality.

This module keeps the source Werner parameter separate from ``channel_state``.
The channel still emits the source/resource quality unchanged; this layer computes
an effective Werner parameter from signal coincidences and accidental background
coincidences.

Physics:
    eta_link = transmittance * detector_efficiency
    S = pair_rate_hz * alice_efficiency * eta_link
    B = background_rate_hz * local_singles_rate_hz * coincidence_window_s
      = R_bg * (pair_rate_hz * alice_efficiency) * dt
    p_eff = werner_p_source * S / (S + B)

The accidental background term is a product of rates and the coincidence window.
It is independent of link transmittance; link loss affects p_eff only by lowering
the signal coincidence rate S.
"""

from __future__ import annotations


SKY_BACKGROUND_RATE_HZ = {
    "night": 0.0,
    "twilight": 5.0e5,
    "day": 5.0e6,
}

DEFAULT_SOURCE = {
    "pair_rate_hz": 1.0e7,
    "alice_efficiency": 0.6,
    "coincidence_window_s": 1.0e-9,
}


def signal_coincidence_rate(
    transmittance,
    detector_efficiency,
    *,
    pair_rate_hz,
    alice_efficiency,
):
    """Return S = pair_rate * alice_efficiency * transmittance * detector_efficiency."""

    if not 0.0 <= transmittance <= 1.0:
        raise ValueError("transmittance must be in [0, 1].")
    if not 0.0 <= detector_efficiency <= 1.0:
        raise ValueError("detector_efficiency must be in [0, 1].")
    if pair_rate_hz < 0.0:
        raise ValueError("pair_rate_hz must be non-negative.")
    if not 0.0 <= alice_efficiency <= 1.0:
        raise ValueError("alice_efficiency must be in [0, 1].")

    return pair_rate_hz * alice_efficiency * (transmittance * detector_efficiency)


def background_coincidence_rate(
    background_rate_hz,
    coincidence_window_s,
    *,
    local_singles_rate_hz,
):
    """Return accidentals B = background_rate_hz * local_singles_rate_hz * window."""

    if background_rate_hz < 0.0:
        raise ValueError("background_rate_hz must be non-negative.")
    if coincidence_window_s <= 0.0:
        raise ValueError("coincidence_window_s must be positive.")
    if local_singles_rate_hz < 0.0:
        raise ValueError("local_singles_rate_hz must be non-negative.")

    return background_rate_hz * local_singles_rate_hz * coincidence_window_s


def effective_werner_p(
    transmittance,
    werner_p_source,
    detector_efficiency,
    *,
    background_rate_hz=0.0,
    pair_rate_hz=DEFAULT_SOURCE["pair_rate_hz"],
    alice_efficiency=DEFAULT_SOURCE["alice_efficiency"],
    coincidence_window_s=DEFAULT_SOURCE["coincidence_window_s"],
):
    """Return p_eff = p_source * S / (S + B) under background contamination."""

    if not 0.0 <= werner_p_source <= 1.0:
        raise ValueError("werner_p_source must be in [0, 1].")

    signal_rate_hz = signal_coincidence_rate(
        transmittance,
        detector_efficiency,
        pair_rate_hz=pair_rate_hz,
        alice_efficiency=alice_efficiency,
    )
    local_singles_rate_hz = pair_rate_hz * alice_efficiency
    background_rate = background_coincidence_rate(
        background_rate_hz,
        coincidence_window_s,
        local_singles_rate_hz=local_singles_rate_hz,
    )

    total_rate_hz = signal_rate_hz + background_rate
    if total_rate_hz == 0.0:
        return 0.0
    return werner_p_source * signal_rate_hz / total_rate_hz


def effective_werner_p_for_sky(
    transmittance,
    werner_p_source,
    detector_efficiency,
    *,
    sky_condition="night",
    **source_overrides,
):
    """Return effective Werner-p using a named illustrative sky background."""

    if sky_condition not in SKY_BACKGROUND_RATE_HZ:
        raise ValueError(
            f"unknown sky_condition {sky_condition!r}; "
            f"choose from {sorted(SKY_BACKGROUND_RATE_HZ)}"
        )
    return effective_werner_p(
        transmittance,
        werner_p_source,
        detector_efficiency,
        background_rate_hz=SKY_BACKGROUND_RATE_HZ[sky_condition],
        **source_overrides,
    )
