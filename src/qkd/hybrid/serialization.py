"""D-H1-3: canonical JSON encoding, decoding, and digests for hybrid records.

Canonical form (pinned exactly by the HYBRID-1 packet, D-H1-3):

- **Envelope:** ``{"record_type": <dataclass name>, "schema_version":
  "hybrid-1.0", "payload": {...}}``; ``record_type`` is the dataclass name;
  the digest is computed over the full envelope bytes.
- **Canonical encoding:** UTF-8, ``ensure_ascii=True``, sorted keys at every
  level, ``separators=(",", ":")`` (no whitespace variance), NaN/Inf rejected
  both at construction (the dataclasses' own ``__post_init__``) and here at
  encoding time.
- **Canonical floats:** Python's default ``json`` float encoder already uses
  ``repr(float)`` (CPython's shortest round-trip decimal) -- no custom float
  formatting is introduced here.
- **Loader round-trip guard:** :func:`from_canonical_json` re-serializes the
  parsed object under these same rules and rejects any input whose bytes
  differ -- non-canonical spellings never load.
- **Hash algorithm:** SHA-256 over the canonical envelope bytes, hex-lowercase
  (:func:`stable_hash`).

This module is fully generic: it derives each field's wire shape from the
dataclass's own type hints (via :func:`typing.get_type_hints`), so it needs no
per-record-type registry and therefore no project-internal import of
``qkd.hybrid.states``, ``qkd.hybrid.registry``, or ``qkd.adaptive.contracts``
-- callers pass the record instance (:func:`to_canonical_json`) or the
expected class (:func:`from_canonical_json`) explicitly. Supported field
shapes: ``str``, ``int``, ``float``, ``bool``, ``str | None``, a ``str``-based
``Enum``, ``tuple[str, ...]``, ``tuple[<Enum>, ...]``, a frozen string mapping
(``tuple[tuple[str, str], ...]``), a frozen object mapping
(``tuple[tuple[str, <dataclass>], ...]``, e.g. ``RegistrySnapshot.postures``),
and a directly nested frozen dataclass. Any other annotation (in particular
``bytes``) is rejected -- see the "Stage 1 contract set never carries raw key
bytes" invariant.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import math
import types
import typing

SCHEMA_VERSION = "hybrid-1.0"

_ENVELOPE_KEYS = frozenset({"record_type", "schema_version", "payload"})


class SerializationError(ValueError):
    """Raised for canonical-encoding, decoding, or round-trip violations."""


class _Kind(enum.Enum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    ENUM = "enum"
    OPTIONAL_STR = "optional_str"
    TUPLE_STR = "tuple_str"
    TUPLE_ENUM = "tuple_enum"
    STR_MAP = "str_map"
    OBJ_MAP = "obj_map"
    NESTED = "nested"


def _classify(tp: object) -> tuple[_Kind, object | None]:
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)

    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            elem = args[0]
            elem_origin = typing.get_origin(elem)
            elem_args = typing.get_args(elem)
            if elem is str:
                return _Kind.TUPLE_STR, None
            if isinstance(elem, type) and issubclass(elem, enum.Enum):
                return _Kind.TUPLE_ENUM, elem
            if elem_origin is tuple and len(elem_args) == 2 and elem_args[0] is str:
                value_type = elem_args[1]
                if value_type is str:
                    return _Kind.STR_MAP, None
                if dataclasses.is_dataclass(value_type):
                    return _Kind.OBJ_MAP, value_type
        raise SerializationError(f"Unsupported tuple field type for hybrid serialization: {tp!r}.")

    if origin is typing.Union or origin is types.UnionType:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and type(None) in args and non_none[0] is str:
            return _Kind.OPTIONAL_STR, None
        raise SerializationError(f"Unsupported union field type for hybrid serialization: {tp!r}.")

    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return _Kind.ENUM, tp

    if tp is str:
        return _Kind.STR, None
    if tp is bool:
        return _Kind.BOOL, None
    if tp is int:
        return _Kind.INT, None
    if tp is float:
        return _Kind.FLOAT, None

    if dataclasses.is_dataclass(tp):
        return _Kind.NESTED, tp

    raise SerializationError(
        f"Unsupported field type for hybrid canonical serialization: {tp!r} "
        "(no field may be typed 'bytes' -- Stage 1 carries no raw key material)."
    )


def _field_hints(cls: type) -> dict[str, object]:
    return typing.get_type_hints(cls)


# ---------------------------------------------------------------------------
# Encode: dataclass instance -> JSON-compatible payload
# ---------------------------------------------------------------------------


def _encode_value(value: object, kind: _Kind, arg: object | None, path: str) -> object:
    if kind is _Kind.STR:
        if not isinstance(value, str):
            raise SerializationError(f"{path} must be a str; got {value!r}.")
        return value
    if kind is _Kind.BOOL:
        if not isinstance(value, bool):
            raise SerializationError(f"{path} must be a bool; got {value!r}.")
        return value
    if kind is _Kind.INT:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SerializationError(f"{path} must be an int; got {value!r}.")
        return value
    if kind is _Kind.FLOAT:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SerializationError(f"{path} must be a float; got {value!r}.")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise SerializationError(f"{path} must be finite; got {value!r}.")
        return numeric
    if kind is _Kind.ENUM:
        if not isinstance(value, arg):
            raise SerializationError(f"{path} must be a {arg.__name__}; got {value!r}.")
        return value.value
    if kind is _Kind.OPTIONAL_STR:
        if value is None:
            return None
        if not isinstance(value, str):
            raise SerializationError(f"{path} must be a str or None; got {value!r}.")
        return value
    if kind is _Kind.TUPLE_STR:
        if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
            raise SerializationError(f"{path} must be a tuple[str, ...]; got {value!r}.")
        return list(value)
    if kind is _Kind.TUPLE_ENUM:
        if not isinstance(value, tuple) or any(not isinstance(item, arg) for item in value):
            raise SerializationError(f"{path} must be a tuple[{arg.__name__}, ...]; got {value!r}.")
        return [item.value for item in value]
    if kind is _Kind.STR_MAP:
        if not isinstance(value, tuple):
            raise SerializationError(f"{path} must be a tuple[tuple[str, str], ...]; got {value!r}.")
        result: dict[str, str] = {}
        for item in value:
            if not (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], str)
            ):
                raise SerializationError(f"{path} entries must be (str, str) pairs; got {item!r}.")
            result[item[0]] = item[1]
        return result
    if kind is _Kind.OBJ_MAP:
        if not isinstance(value, tuple):
            raise SerializationError(f"{path} must be a tuple[tuple[str, ...], ...]; got {value!r}.")
        result_obj: dict[str, object] = {}
        for item in value:
            if not (isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)):
                raise SerializationError(f"{path} entries must be (str, <object>) pairs; got {item!r}.")
            key, obj = item
            if not isinstance(obj, arg):
                raise SerializationError(f"{path}[{key!r}] must be a {arg.__name__}; got {obj!r}.")
            result_obj[key] = _encode_dataclass(obj)
        return result_obj
    if kind is _Kind.NESTED:
        if not isinstance(value, arg):
            raise SerializationError(f"{path} must be a {arg.__name__}; got {value!r}.")
        return _encode_dataclass(value)
    raise AssertionError(kind)  # pragma: no cover - exhaustive above


def _encode_dataclass(instance: object) -> dict[str, object]:
    cls = type(instance)
    hints = _field_hints(cls)
    payload: dict[str, object] = {}
    for f in dataclasses.fields(cls):
        kind, arg = _classify(hints[f.name])
        payload[f.name] = _encode_value(getattr(instance, f.name), kind, arg, f.name)
    return payload


def _dumps(obj: object) -> bytes:
    text = json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    return text.encode("utf-8")


def to_canonical_json(record: object) -> bytes:
    """Encode ``record`` (any frozen dataclass instance) to canonical envelope bytes."""

    if not dataclasses.is_dataclass(record) or isinstance(record, type):
        raise SerializationError("to_canonical_json requires a dataclass instance.")
    envelope = {
        "record_type": type(record).__name__,
        "schema_version": SCHEMA_VERSION,
        "payload": _encode_dataclass(record),
    }
    return _dumps(envelope)


# ---------------------------------------------------------------------------
# Decode: JSON payload -> dataclass instance
# ---------------------------------------------------------------------------


def _decode_value(value: object, kind: _Kind, arg: object | None, path: str) -> object:
    if kind is _Kind.STR:
        if not isinstance(value, str):
            raise SerializationError(f"{path} must be a string.")
        return value
    if kind is _Kind.BOOL:
        if not isinstance(value, bool):
            raise SerializationError(f"{path} must be a bool.")
        return value
    if kind is _Kind.INT:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SerializationError(f"{path} must be an int.")
        return value
    if kind is _Kind.FLOAT:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SerializationError(f"{path} must be a number.")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise SerializationError(f"{path} must be finite.")
        return numeric
    if kind is _Kind.ENUM:
        if not isinstance(value, str):
            raise SerializationError(f"{path} must be a string enum value.")
        try:
            return arg(value)
        except ValueError as exc:
            raise SerializationError(f"{path} has unknown enum value {value!r}.") from exc
    if kind is _Kind.OPTIONAL_STR:
        if value is None:
            return None
        if not isinstance(value, str):
            raise SerializationError(f"{path} must be a string or null.")
        return value
    if kind is _Kind.TUPLE_STR:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise SerializationError(f"{path} must be an array of strings.")
        return tuple(value)
    if kind is _Kind.TUPLE_ENUM:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise SerializationError(f"{path} must be an array of strings.")
        try:
            return tuple(arg(item) for item in value)
        except ValueError as exc:
            raise SerializationError(f"{path} has an unknown enum value: {exc}") from exc
    if kind is _Kind.STR_MAP:
        if not isinstance(value, dict):
            raise SerializationError(f"{path} must be an object.")
        for k, v in value.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise SerializationError(f"{path} must map strings to strings.")
        return tuple(sorted(value.items()))
    if kind is _Kind.OBJ_MAP:
        if not isinstance(value, dict):
            raise SerializationError(f"{path} must be an object.")
        items = []
        for k, v in value.items():
            if not isinstance(k, str) or not isinstance(v, dict):
                raise SerializationError(f"{path} entries must map string keys to objects.")
            items.append((k, _decode_dataclass(arg, v, f"{path}.{k}")))
        items.sort(key=lambda kv: kv[0])
        return tuple(items)
    if kind is _Kind.NESTED:
        if not isinstance(value, dict):
            raise SerializationError(f"{path} must be an object.")
        return _decode_dataclass(arg, value, path)
    raise AssertionError(kind)  # pragma: no cover - exhaustive above


def _decode_dataclass(cls: type, payload: object, path: str) -> object:
    if not isinstance(payload, dict):
        raise SerializationError(f"{path} must be an object.")
    hints = _field_hints(cls)
    field_names = {f.name for f in dataclasses.fields(cls)}
    extra = set(payload) - field_names
    if extra:
        raise SerializationError(f"{path} has unknown key(s): {sorted(extra)}.")
    missing = field_names - set(payload)
    if missing:
        raise SerializationError(f"{path} is missing required key(s): {sorted(missing)}.")
    kwargs = {}
    for f in dataclasses.fields(cls):
        kind, arg = _classify(hints[f.name])
        kwargs[f.name] = _decode_value(payload[f.name], kind, arg, f"{path}.{f.name}")
    try:
        return cls(**kwargs)
    except (ValueError, TypeError) as exc:
        raise SerializationError(f"{path}: invalid record: {exc}") from exc


def from_canonical_json(data: bytes, cls: type) -> object:
    """Decode canonical envelope ``data`` into an instance of ``cls``.

    Rejects any input whose canonical reserialization differs byte-for-byte
    from ``data`` (non-canonical spellings never load), and any envelope or
    payload with unknown or missing keys.
    """

    if not isinstance(data, (bytes, bytearray)):
        raise SerializationError("from_canonical_json requires bytes input.")
    try:
        text = bytes(data).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SerializationError(f"Input is not valid UTF-8: {exc}") from exc
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SerializationError(f"Input is not valid JSON: {exc}") from exc
    if not isinstance(envelope, dict):
        raise SerializationError("Envelope must be a JSON object.")
    extra = set(envelope) - _ENVELOPE_KEYS
    if extra:
        raise SerializationError(f"Envelope has unknown key(s): {sorted(extra)}.")
    missing = _ENVELOPE_KEYS - set(envelope)
    if missing:
        raise SerializationError(f"Envelope is missing key(s): {sorted(missing)}.")

    record_type = envelope["record_type"]
    if record_type != cls.__name__:
        raise SerializationError(
            f"record_type={record_type!r} does not match expected {cls.__name__!r}."
        )
    schema_version = envelope["schema_version"]
    if schema_version != SCHEMA_VERSION:
        raise SerializationError(f"schema_version={schema_version!r} does not match {SCHEMA_VERSION!r}.")

    instance = _decode_dataclass(cls, envelope["payload"], "payload")

    reencoded = to_canonical_json(instance)
    if reencoded != bytes(data):
        raise SerializationError(
            "Input does not equal its own canonical reserialization; "
            "non-canonical spellings are refused (D-H1-3 loader round-trip guard)."
        )
    return instance


def stable_hash(data: bytes) -> str:
    """SHA-256 hex-lowercase digest of ``data`` (already-lowercase per ``hexdigest``)."""

    if not isinstance(data, (bytes, bytearray)):
        raise SerializationError("stable_hash requires bytes input.")
    return hashlib.sha256(bytes(data)).hexdigest()
