"""Provenance tags for emitted simulator quantities."""

from __future__ import annotations

from enum import Enum


class Provenance(str, Enum):
    """Observational origin tags; tags describe values and never change them."""

    ANALYTIC = "ANALYTIC"
    SIMULATED = "SIMULATED"
    DERIVED = "DERIVED"
    ILLUSTRATIVE = "ILLUSTRATIVE"
    MEASURED = "MEASURED"
    ESTIMATED = "ESTIMATED"
    VALIDATED = "VALIDATED"
