"""HYBRID-1 canonical serialization pinned to schema ``hybrid-1.0``.

The encoding mechanism is schema-neutral and lives in :mod:`qkd.canonical`.
This compatibility wrapper preserves the original HYBRID public API and wire
bytes while keeping semantic schema ownership at the call site.
"""

from __future__ import annotations

from qkd.canonical import SerializationError, stable_hash
from qkd.canonical import from_canonical_json as _from_canonical_json
from qkd.canonical import to_canonical_json as _to_canonical_json

SCHEMA_VERSION = "hybrid-1.0"


def to_canonical_json(record: object) -> bytes:
    """Encode a HYBRID record using the frozen HYBRID schema identity."""

    return _to_canonical_json(record, schema_version=SCHEMA_VERSION)


def from_canonical_json(data: bytes, cls: type) -> object:
    """Decode canonical HYBRID bytes into ``cls``."""

    return _from_canonical_json(data, cls, schema_version=SCHEMA_VERSION)


__all__ = [
    "SCHEMA_VERSION",
    "SerializationError",
    "from_canonical_json",
    "stable_hash",
    "to_canonical_json",
]
