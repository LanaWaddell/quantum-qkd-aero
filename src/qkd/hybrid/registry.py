"""HYBRID-1 Deliverable 3: algorithm-posture registry snapshot interface.

``AlgorithmPostureRegistry`` follows the project's D3 registry pattern
(LINK-1): an **independent** registry, its own module, its own declared
contents, with **no coupling to** ``qkd.schema.DECLARED_SCHEMA_EXTENSIONS`` --
mirrored, not shared, exactly as LINK-1's controls registry mirrors rather
than shares the schema-extension registry.

Read-only snapshot semantics: :class:`RegistrySnapshot` is frozen and carries
no stored digest field (C8) -- a digest stored *inside* the snapshot cannot be
computed over the full envelope that contains it. The canonical digest is
instead a **computed property**, :meth:`RegistrySnapshot.digest`, over the
snapshot's own (digest-free) canonical envelope bytes via
:func:`qkd.hybrid.serialization.stable_hash`. Policy evaluation (Stage 2)
consumes snapshots, never the live registry.

The mandatory CI consistency test (D3) lives in
``tests/test_hybrid_registry.py`` and exercises
:meth:`AlgorithmPostureRegistry.check_consistency` against both a valid
registry and a deliberately corrupted one, so the check is proven real, not
tautological.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from qkd.hybrid.serialization import stable_hash, to_canonical_json
from qkd.hybrid.states import (
    AlgorithmPosture,
    CryptoPostureStatus,
    _require_nonempty_str,
    _require_timestamp,
)

__all__ = ["RegistryError", "RegistrySnapshot", "AlgorithmPostureRegistry", "KNOWN_POSTURE_STATUSES"]


class RegistryError(ValueError):
    """Raised for registry construction, registration, or consistency errors."""


KNOWN_POSTURE_STATUSES: tuple[str, ...] = (
    "approved",
    "watched",
    "contested",
    "deprecated",
    "disallowed",
    "unknown",
)
"""Serialized vocabulary constant, deliberately maintained separately from
:class:`qkd.hybrid.states.CryptoPostureStatus` (D3 mirror-don't-share) so the
CI consistency test can catch drift between the enum and this registry's
declared vocabulary, rather than the check being definitionally true."""


def _freeze_postures(
    value: object, field_name: str = "postures"
) -> tuple[tuple[str, AlgorithmPosture], ...]:
    if isinstance(value, dict):
        items = list(value.items())
    elif isinstance(value, tuple):
        items = list(value)
    else:
        raise TypeError(
            f"{field_name} must be a dict[str, AlgorithmPosture] or "
            f"tuple[tuple[str, AlgorithmPosture], ...]; got {type(value)!r}."
        )
    pairs: list[tuple[str, AlgorithmPosture]] = []
    for item in items:
        if not (isinstance(item, tuple) and len(item) == 2):
            raise TypeError(f"{field_name} entries must be (str, AlgorithmPosture) pairs; got {item!r}.")
        suite_id, posture = item
        if not isinstance(suite_id, str) or suite_id == "":
            raise ValueError(f"{field_name} keys must be non-empty strings; got {suite_id!r}.")
        if not isinstance(posture, AlgorithmPosture):
            raise TypeError(f"{field_name}[{suite_id!r}] must be an AlgorithmPosture; got {posture!r}.")
        if posture.suite_id != suite_id:
            raise ValueError(
                f"{field_name}[{suite_id!r}].suite_id={posture.suite_id!r} does not match its key."
            )
        pairs.append((suite_id, posture))
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{field_name} has duplicate suite ids.")
    pairs.sort(key=lambda kv: kv[0])
    return tuple(pairs)


@dataclass(frozen=True)
class RegistrySnapshot:
    """A read-only, digest-free snapshot of an :class:`AlgorithmPostureRegistry`.

    Freshness is defined on the snapshot as data (``produced_at_utc`` plus a
    staleness rule evaluated by Stage 2's policy engine) -- no evaluation
    happens here.
    """

    registry_version: str
    produced_at_utc: str
    postures: tuple[tuple[str, AlgorithmPosture], ...]

    def __post_init__(self) -> None:
        _require_nonempty_str(self.registry_version, "registry_version")
        _require_timestamp(self.produced_at_utc, "produced_at_utc")
        object.__setattr__(self, "postures", _freeze_postures(self.postures, "postures"))

    def digest(self) -> str:
        """SHA-256 hex-lowercase over this snapshot's own canonical envelope bytes.

        Computed, never stored: the envelope this hashes contains no digest
        field, so there is no self-reference (C8)."""

        return stable_hash(to_canonical_json(self))


class AlgorithmPostureRegistry:
    """Independent posture registry (D3 pattern) -- construction-time and
    live registration are both declared-or-fail: every registered suite id
    must be unique and every posture's own ``suite_id`` must match its key."""

    def __init__(self, *, postures: Iterable[AlgorithmPosture] = ()) -> None:
        self._postures: dict[str, AlgorithmPosture] = {}
        for posture in postures:
            self.register(posture)

    def register(self, posture: AlgorithmPosture) -> None:
        if not isinstance(posture, AlgorithmPosture):
            raise TypeError(f"register() requires an AlgorithmPosture; got {posture!r}.")
        if posture.suite_id in self._postures:
            raise RegistryError(f"suite_id {posture.suite_id!r} is already registered.")
        self._postures[posture.suite_id] = posture

    def suite_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._postures))

    def get(self, suite_id: str) -> AlgorithmPosture:
        try:
            return self._postures[suite_id]
        except KeyError as exc:
            raise RegistryError(f"suite_id {suite_id!r} is not registered.") from exc

    def snapshot(self, *, registry_version: str, produced_at_utc: str) -> RegistrySnapshot:
        return RegistrySnapshot(
            registry_version=registry_version,
            produced_at_utc=produced_at_utc,
            postures=dict(self._postures),
        )

    def check_consistency(self) -> None:
        """D3 mandatory CI consistency check: registry contents, enum
        vocabularies, and serialized vocabulary constants must not drift
        apart. Raises :class:`RegistryError` on any drift."""

        known = frozenset(KNOWN_POSTURE_STATUSES)
        enum_values = frozenset(status.value for status in CryptoPostureStatus)
        if known != enum_values:
            raise RegistryError(
                "KNOWN_POSTURE_STATUSES has drifted from CryptoPostureStatus: "
                f"registry={sorted(known)} enum={sorted(enum_values)}."
            )
        for suite_id, posture in self._postures.items():
            if posture.suite_id != suite_id:
                raise RegistryError(
                    f"registry entry key {suite_id!r} does not match posture.suite_id "
                    f"{posture.suite_id!r}."
                )
            if posture.status.value not in known:
                raise RegistryError(
                    f"suite_id {suite_id!r} has status {posture.status.value!r}, "
                    f"not in the declared vocabulary {sorted(known)}."
                )
