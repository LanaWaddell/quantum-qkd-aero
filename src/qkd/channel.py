import math
import random

from qkd.signals import ChannelState


DEFAULT_ATMOSPHERE = {
    "zenith_optical_depth": 0.20,
    "system_efficiency": 0.50,
    "beam_divergence_urad": 10.0,
    "rx_aperture_m": 0.50,
    "intrinsic_qber": 0.015,
    "dark_count_prob": 1.0e-6,
    "werner_p": 0.98,
}


def apply_loss(bit, p_loss, rng=None):
    rng = rng or random
    if rng.random() < p_loss:
        return None
    return bit


def apply_bit_flip(bit, p_flip, rng=None):
    rng = rng or random
    if rng.random() < p_flip:
        return 1 - bit
    return bit


def transmit_bit(bit, p_loss=0.0, p_flip=0.0, rng=None):
    transmitted = apply_loss(bit, p_loss, rng=rng)
    if transmitted is None:
        return None
    return apply_bit_flip(transmitted, p_flip, rng=rng)


def fidelity_noise(frame_index, base_fidelity, noise_strength=0.05, p_loss=0.0, p_flip=0.0):
    jitter = math.sin(frame_index / 50) * noise_strength
    # TODO(2B-3): This is legacy/decorative simulator noise. Replace it when
    # run.py is rewired to use teleportation_fidelity(werner_p).
    # Scale loss and bit-flip probabilities into a simple fidelity degradation term.
    penalty = (p_loss * 0.02) + (p_flip * 0.1)
    fidelity = base_fidelity + jitter - penalty
    return max(0.0, min(1.0, fidelity))


def atmospheric_transmittance(elevation_deg, zenith_optical_depth):
    """Return atmospheric transmittance for a simple airmass model."""

    if elevation_deg <= 0.0 or elevation_deg > 90.0:
        raise ValueError("elevation_deg must be in the interval (0, 90]")
    if zenith_optical_depth < 0.0:
        raise ValueError("zenith_optical_depth must be non-negative")

    airmass = 1.0 / math.sin(math.radians(elevation_deg))
    return math.exp(-zenith_optical_depth * airmass)


def geometric_transmittance(slant_range_km, beam_divergence_urad, rx_aperture_m):
    """Return Gaussian beam fraction coupled into a receiver aperture diameter."""

    if slant_range_km < 0.0:
        raise ValueError("slant_range_km must be non-negative")
    if beam_divergence_urad < 0.0:
        raise ValueError("beam_divergence_urad must be non-negative")
    if rx_aperture_m < 0.0:
        raise ValueError("rx_aperture_m must be non-negative")

    slant_range_m = slant_range_km * 1_000.0
    beam_radius_m = beam_divergence_urad * 1.0e-6 * slant_range_m
    if beam_radius_m <= 0.0:
        return 1.0

    aperture_radius_m = rx_aperture_m / 2.0
    return 1.0 - math.exp(-2.0 * aperture_radius_m**2 / beam_radius_m**2)


def channel_state(
    elevation_deg,
    slant_range_km,
    atmosphere=None,
    *,
    eta_override=None,
    p_override=None,
):
    """Resolve geometric/atmospheric link inputs into a ChannelState."""

    cfg = dict(DEFAULT_ATMOSPHERE)
    if atmosphere:
        cfg.update(atmosphere)

    if eta_override is None:
        eta = (
            cfg["system_efficiency"]
            * atmospheric_transmittance(elevation_deg, cfg["zenith_optical_depth"])
            * geometric_transmittance(
                slant_range_km,
                cfg["beam_divergence_urad"],
                cfg["rx_aperture_m"],
            )
        )
    else:
        eta = eta_override

    eta = max(0.0, min(1.0, eta))

    # Werner resource quality is intentionally independent of atmospheric loss.
    # It changes only through explicit source/resource-quality configuration.
    werner_p = cfg["werner_p"] if p_override is None else p_override
    werner_p = max(0.0, min(1.0, werner_p))

    return ChannelState(
        transmittance=eta,
        werner_p=werner_p,
        intrinsic_qber=cfg["intrinsic_qber"],
        dark_count_prob=cfg["dark_count_prob"],
        slant_range_km=slant_range_km,
        elevation_deg=elevation_deg,
    )
