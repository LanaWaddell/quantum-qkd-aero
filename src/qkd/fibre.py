"""Dedicated-fibre channel front-end for the ChannelState contract.

The constants are illustrative, representative defaults rather than calibrated
deployment data. This module models a dark/dedicated fibre link; Raman noise
from classical DWDM co-propagation is a deferred background-light refinement.
"""

from __future__ import annotations

from qkd.signals import ChannelState


DEFAULT_FIBRE = {
    "attenuation_db_km": 0.2,
    "fixed_loss_db": 6.0,
    "intrinsic_qber": 0.015,
    "dark_count_prob": 1.0e-6,
    "werner_p": 0.98,
}
"""Illustrative fibre-link parameters.

``attenuation_db_km=0.2`` is the standard single-mode telecom-fibre figure near
1550 nm; ultra-low-loss fibre can be represented with values around 0.16 dB/km.
``fixed_loss_db`` represents aggregate insertion/coupling loss.
"""


def fibre_transmittance(
    length_km,
    attenuation_db_km=DEFAULT_FIBRE["attenuation_db_km"],
    fixed_loss_db=DEFAULT_FIBRE["fixed_loss_db"],
) -> float:
    """Return fibre transmittance from attenuation and fixed insertion loss."""

    if length_km < 0.0:
        raise ValueError("length_km must be non-negative.")
    if attenuation_db_km < 0.0:
        raise ValueError("attenuation_db_km must be non-negative.")
    if fixed_loss_db < 0.0:
        raise ValueError("fixed_loss_db must be non-negative.")

    total_loss_db = (attenuation_db_km * length_km) + fixed_loss_db
    eta = 10.0 ** (-total_loss_db / 10.0)
    return max(0.0, min(1.0, eta))


def fibre_channel_state(
    length_km,
    fibre=None,
    *,
    eta_override=None,
    p_override=None,
) -> ChannelState:
    """Resolve a dedicated-fibre link into a geometry-free ChannelState."""

    cfg = dict(DEFAULT_FIBRE)
    if fibre:
        cfg.update(fibre)

    if eta_override is None:
        eta = fibre_transmittance(
            length_km,
            cfg["attenuation_db_km"],
            cfg["fixed_loss_db"],
        )
    else:
        if not 0.0 <= eta_override <= 1.0:
            raise ValueError("eta_override must be in [0, 1].")
        eta = eta_override

    if p_override is None:
        werner_p = cfg["werner_p"]
    else:
        if not 0.0 <= p_override <= 1.0:
            raise ValueError("p_override must be in [0, 1].")
        werner_p = p_override

    return ChannelState(
        transmittance=eta,
        werner_p=werner_p,
        intrinsic_qber=cfg["intrinsic_qber"],
        dark_count_prob=cfg["dark_count_prob"],
        slant_range_km=None,
        elevation_deg=None,
    )
