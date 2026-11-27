"""URL-safe object keys and request-scoped continuation tokens."""

import base64
import hashlib
import json
import re
import zlib
from collections.abc import Callable, Sequence
from uuid import UUID

from ontology_platform.errors import AppError
from ontology_platform.modules.connectors.schemas import CatalogColumn
from ontology_platform.modules.connectors.statements import Value
from ontology_platform.modules.query import errors, schemas, values

# Includes up to eight key columns and two sort values, with JSON escaping.
_MAX_DECODED = 128 * 1024


def _bytes(data: object) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _encode(data: object, limit: int, overflow: Callable[[], AppError]) -> str:
    raw = _bytes(data)
    if len(raw) > _MAX_DECODED:
        raise overflow()
    if len(raw) * 4 > limit * 3:
        raw = b"\x00" + zlib.compress(raw)
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    if len(encoded) > limit:
        raise overflow()
    return encoded


def _decode(token: str, limit: int) -> object:
    if len(token) > limit or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ValueError
    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != token:
        raise ValueError
    if raw.startswith(b"\x00"):
        stream = zlib.decompressobj()
        try:
            raw = stream.decompress(raw[1:], max_length=_MAX_DECODED + 1)
        except zlib.error as exc:
            raise ValueError from exc
        if len(raw) > _MAX_DECODED or not stream.eof or stream.unused_data:
            raise ValueError
    return json.loads(raw.decode("utf-8"))


def encode_key(parts: list[str]) -> str:
    return _encode(parts, schemas.KEY_MAX_LENGTH, errors.source_mismatch)


def decode_key(token: str, columns: Sequence[CatalogColumn]) -> tuple[Value, ...]:
    try:
        parts = _decode(token, schemas.KEY_MAX_LENGTH)
        if not isinstance(parts, list) or len(columns) != len(parts):
            raise ValueError
        if not all(isinstance(part, str) for part in parts):
            raise ValueError
        return tuple(
            values.parse_value(part, col) for part, col in zip(parts, columns, strict=True)
        )
    except (ValueError, RecursionError):
        raise errors.object_not_found() from None


def search_context(body: schemas.ObjectSearch) -> dict[str, object]:
    filters = [item.model_dump(mode="json") for item in body.filters]
    return {
        "type": str(body.type_id),
        "sort": [[str(item.property_id), item.direction] for item in body.sort],
        "filters": hashlib.sha256(_bytes(filters)).hexdigest(),
    }


def encode_page(release: UUID, context: dict[str, object], position: list[str | None]) -> str:
    # Even compressed, long text sort values can exceed the cursor limit. Keys are bounded by
    # their own limit, so a request without a sort only overflows when the source's keys do.
    overflow = errors.sort_value_too_long if context.get("sort") else errors.source_mismatch
    return _encode([str(release), context, position], schemas.CURSOR_MAX_LENGTH, overflow)


def read_page(
    token: str | None, release: UUID, context: dict[str, object]
) -> list[str | None] | None:
    if token is None:
        return None
    try:
        data = _decode(token, schemas.CURSOR_MAX_LENGTH)
        if not isinstance(data, list) or len(data) != 3:
            raise ValueError
        version, request, position = data
        if not isinstance(version, str) or not isinstance(request, dict):
            raise ValueError
        if not isinstance(position, list) or not position:
            raise ValueError
        if any(value is not None and not isinstance(value, str) for value in position):
            raise ValueError
        if request != context:
            raise ValueError
        if UUID(version) != release:
            raise AppError(409, "query.release_changed", "The active release has changed.")
        return position
    except (ValueError, RecursionError):
        raise errors.invalid_cursor() from None
