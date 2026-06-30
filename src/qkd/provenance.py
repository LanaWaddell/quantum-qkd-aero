"""Provenance tags for emitted simulator quantities."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any


class Provenance(str, Enum):
    """Observational origin tags; tags describe values and never change them."""

    ANALYTIC = "ANALYTIC"
    SIMULATED = "SIMULATED"
    DERIVED = "DERIVED"
    ILLUSTRATIVE = "ILLUSTRATIVE"
    MEASURED = "MEASURED"
    ESTIMATED = "ESTIMATED"
    VALIDATED = "VALIDATED"


DATA_SECTIONS = ("link", "teleportation", "summary", "profile", "geometry", "mission")
RESERVED_TAGS = {
    Provenance.MEASURED.value,
    Provenance.ESTIMATED.value,
    Provenance.VALIDATED.value,
}


class ProvenanceValidationError(ValueError):
    """Raised when emitted data and provenance tags are structurally inconsistent."""


def validate_provenance(
    emitted: Mapping[str, Any],
    provenance_map: Mapping[str, str],
) -> bool:
    """Validate provenance coverage for emitted simulator data leaves.

    A taggable leaf is any non-mapping value reachable under the v2 data
    sections ``link``, ``teleportation``, ``summary``, ``profile``,
    ``geometry``, and ``mission``. Nested mappings recurse; arrays/lists/tuples
    are intentionally treated as single leaves so whole-array tags such as
    ``profile.loss_db`` remain the unit of provenance. Metadata sections such
    as ``schema_version``, ``provenance``, and ``run_metadata`` are outside the
    validation scope.
    """

    if not isinstance(emitted, Mapping):
        raise ProvenanceValidationError("Emitted payload must be a mapping.")
    if not isinstance(provenance_map, Mapping):
        raise ProvenanceValidationError("Provenance map must be a mapping.")

    emitted_leaf_paths = _data_leaf_paths(emitted)
    provenance_paths = set(provenance_map)

    missing = emitted_leaf_paths - provenance_paths
    if missing:
        missing_paths = ", ".join(sorted(missing))
        raise ProvenanceValidationError(f"Missing provenance tags: {missing_paths}")

    extra = provenance_paths - emitted_leaf_paths
    if extra:
        extra_paths = ", ".join(sorted(extra))
        raise ProvenanceValidationError(f"Provenance tags reference non-emitted fields: {extra_paths}")

    known_tags = {tag.value for tag in Provenance}
    for path, tag in provenance_map.items():
        tag_value = tag.value if isinstance(tag, Provenance) else tag
        if tag_value not in known_tags:
            raise ProvenanceValidationError(f"Unknown provenance tag for {path}: {tag_value}")
        if tag_value in RESERVED_TAGS:
            raise ProvenanceValidationError(f"Reserved provenance tag is not yet allowed for {path}: {tag_value}")

    return True


def _data_leaf_paths(emitted: Mapping[str, Any]) -> set[str]:
    leaf_paths: set[str] = set()
    for section in DATA_SECTIONS:
        if section in emitted:
            leaf_paths.update(_leaf_paths(section, emitted[section]))
    return leaf_paths


def _leaf_paths(prefix: str, value: Any) -> set[str]:
    if isinstance(value, Mapping):
        paths: set[str] = set()
        for key, child in value.items():
            paths.update(_leaf_paths(f"{prefix}.{key}", child))
        return paths
    return {prefix}
