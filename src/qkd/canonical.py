"""Schema-neutral canonical JSON encoding for frozen dataclass records.

Semantic schema identity belongs to the caller.  This module supplies only the
canonical mechanism: a fixed envelope, strict type-directed encoding, a
round-trip guard on load, and SHA-256 digests over the resulting bytes.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import math
import types
import typing

_ENVELOPE_KEYS = frozenset({"record_type", "schema_version", "payload"})


class SerializationError(ValueError):
    """Raised for canonical encoding, decoding, or round-trip violations."""


class _Kind(enum.Enum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    ENUM = "enum"
    OPTIONAL_STR = "optional_str"
    TUPLE_STR = "tuple_str"
    TUPLE_FLOAT = "tuple_float"
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
            if elem is float:
                return _Kind.TUPLE_FLOAT, None
            if isinstance(elem, type) and issubclass(elem, enum.Enum):
                return _Kind.TUPLE_ENUM, elem
            if elem_origin is tuple and len(elem_args) == 2 and elem_args[0] is str:
                value_type = elem_args[1]
                if value_type is str:
                    return _Kind.STR_MAP, None
                if dataclasses.is_dataclass(value_type):
                    return _Kind.OBJ_MAP, value_type
        raise SerializationError(f"Unsupported tuple field type for canonical serialization: {tp!r}.")

    if origin is typing.Union or origin is types.UnionType:
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1 and type(None) in args and non_none[0] is str:
            return _Kind.OPTIONAL_STR, None
        raise SerializationError(f"Unsupported union field type for canonical serialization: {tp!r}.")

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
        f"Unsupported field type for canonical serialization: {tp!r} "
        "(raw bytes are not a supported canonical field shape)."
    )


def _field_hints(cls: type) -> dict[str, object]:
    return typing.get_type_hints(cls)


def _finite_float(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SerializationError(f"{path} must be a float; got {value!r}.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise SerializationError(f"{path} must be finite; got {value!r}.")
    return numeric


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
        return _finite_float(value, path)
    if kind is _Kind.ENUM:
        if not isinstance(value, arg):
            raise SerializationError(f"{path} must be a {arg.__name__}; got {value!r}.")
        return value.value
    if kind is _Kind.OPTIONAL_STR:
        if value is not None and not isinstance(value, str):
            raise SerializationError(f"{path} must be a str or None; got {value!r}.")
        return value
    if kind is _Kind.TUPLE_STR:
        if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
            raise SerializationError(f"{path} must be a tuple[str, ...]; got {value!r}.")
        return list(value)
    if kind is _Kind.TUPLE_FLOAT:
        if not isinstance(value, tuple):
            raise SerializationError(f"{path} must be a tuple[float, ...]; got {value!r}.")
        return [_finite_float(item, f"{path}[{index}]") for index, item in enumerate(value)]
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
            if item[0] in result:
                raise SerializationError(f"{path} contains duplicate key {item[0]!r}.")
            result[item[0]] = item[1]
        return result
    if kind is _Kind.OBJ_MAP:
        if not isinstance(value, tuple):
            raise SerializationError(f"{path} must be a tuple of object-map pairs; got {value!r}.")
        result_obj: dict[str, object] = {}
        for item in value:
            if not (isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)):
                raise SerializationError(f"{path} entries must be (str, object) pairs; got {item!r}.")
            key, obj = item
            if key in result_obj:
                raise SerializationError(f"{path} contains duplicate key {key!r}.")
            if not isinstance(obj, arg):
                raise SerializationError(f"{path}[{key!r}] must be a {arg.__name__}; got {obj!r}.")
            result_obj[key] = _encode_dataclass(obj)
        return result_obj
    if kind is _Kind.NESTED:
        if not isinstance(value, arg):
            raise SerializationError(f"{path} must be a {arg.__name__}; got {value!r}.")
        return _encode_dataclass(value)
    raise AssertionError(kind)


def _encode_dataclass(instance: object) -> dict[str, object]:
    cls = type(instance)
    hints = _field_hints(cls)
    payload: dict[str, object] = {}
    for field in dataclasses.fields(cls):
        kind, arg = _classify(hints[field.name])
        payload[field.name] = _encode_value(getattr(instance, field.name), kind, arg, field.name)
    return payload


def _dumps(obj: object) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def to_canonical_json(record: object, *, schema_version: str) -> bytes:
    """Encode a dataclass record to canonical envelope bytes."""

    if not isinstance(schema_version, str) or not schema_version:
        raise SerializationError("schema_version must be a non-empty string.")
    if not dataclasses.is_dataclass(record) or isinstance(record, type):
        raise SerializationError("to_canonical_json requires a dataclass instance.")
    return _dumps(
        {
            "record_type": type(record).__name__,
            "schema_version": schema_version,
            "payload": _encode_dataclass(record),
        }
    )


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
        return _finite_float(value, path)
    if kind is _Kind.ENUM:
        if not isinstance(value, str):
            raise SerializationError(f"{path} must be a string enum value.")
        try:
            return arg(value)
        except ValueError as exc:
            raise SerializationError(f"{path} has unknown enum value {value!r}.") from exc
    if kind is _Kind.OPTIONAL_STR:
        if value is not None and not isinstance(value, str):
            raise SerializationError(f"{path} must be a string or null.")
        return value
    if kind is _Kind.TUPLE_STR:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise SerializationError(f"{path} must be an array of strings.")
        return tuple(value)
    if kind is _Kind.TUPLE_FLOAT:
        if not isinstance(value, list):
            raise SerializationError(f"{path} must be an array of finite numbers.")
        return tuple(_finite_float(item, f"{path}[{index}]") for index, item in enumerate(value))
    if kind is _Kind.TUPLE_ENUM:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise SerializationError(f"{path} must be an array of strings.")
        try:
            return tuple(arg(item) for item in value)
        except ValueError as exc:
            raise SerializationError(f"{path} has an unknown enum value: {exc}") from exc
    if kind is _Kind.STR_MAP:
        if not isinstance(value, dict) or any(
            not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()
        ):
            raise SerializationError(f"{path} must map strings to strings.")
        return tuple(sorted(value.items()))
    if kind is _Kind.OBJ_MAP:
        if not isinstance(value, dict):
            raise SerializationError(f"{path} must be an object.")
        items = []
        for key, item in value.items():
            if not isinstance(key, str) or not isinstance(item, dict):
                raise SerializationError(f"{path} entries must map string keys to objects.")
            items.append((key, _decode_dataclass(arg, item, f"{path}.{key}")))
        return tuple(sorted(items, key=lambda pair: pair[0]))
    if kind is _Kind.NESTED:
        if not isinstance(value, dict):
            raise SerializationError(f"{path} must be an object.")
        return _decode_dataclass(arg, value, path)
    raise AssertionError(kind)


def _decode_dataclass(cls: type, payload: object, path: str) -> object:
    if not isinstance(payload, dict):
        raise SerializationError(f"{path} must be an object.")
    hints = _field_hints(cls)
    field_names = {field.name for field in dataclasses.fields(cls)}
    extra = set(payload) - field_names
    missing = field_names - set(payload)
    if extra:
        raise SerializationError(f"{path} has unknown key(s): {sorted(extra)}.")
    if missing:
        raise SerializationError(f"{path} is missing required key(s): {sorted(missing)}.")
    kwargs = {}
    for field in dataclasses.fields(cls):
        kind, arg = _classify(hints[field.name])
        kwargs[field.name] = _decode_value(payload[field.name], kind, arg, f"{path}.{field.name}")
    try:
        return cls(**kwargs)
    except (ValueError, TypeError) as exc:
        raise SerializationError(f"{path}: invalid record: {exc}") from exc


def from_canonical_json(data: bytes, cls: type, *, schema_version: str) -> object:
    """Decode canonical bytes and reject any noncanonical spelling."""

    if not isinstance(schema_version, str) or not schema_version:
        raise SerializationError("schema_version must be a non-empty string.")
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
    missing = _ENVELOPE_KEYS - set(envelope)
    if extra:
        raise SerializationError(f"Envelope has unknown key(s): {sorted(extra)}.")
    if missing:
        raise SerializationError(f"Envelope is missing key(s): {sorted(missing)}.")
    if envelope["record_type"] != cls.__name__:
        raise SerializationError(
            f"record_type={envelope['record_type']!r} does not match expected {cls.__name__!r}."
        )
    if envelope["schema_version"] != schema_version:
        raise SerializationError(
            f"schema_version={envelope['schema_version']!r} does not match {schema_version!r}."
        )
    instance = _decode_dataclass(cls, envelope["payload"], "payload")
    if to_canonical_json(instance, schema_version=schema_version) != bytes(data):
        raise SerializationError(
            "Input does not equal its own canonical reserialization; non-canonical spellings are refused."
        )
    return instance


def stable_hash(data: bytes) -> str:
    """Return a lowercase SHA-256 digest of canonical bytes."""

    if not isinstance(data, (bytes, bytearray)):
        raise SerializationError("stable_hash requires bytes input.")
    return hashlib.sha256(bytes(data)).hexdigest()
