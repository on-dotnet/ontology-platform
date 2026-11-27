"""Stable errors at the object-query boundary."""

from collections.abc import Sequence

from ontology_platform.errors import AppError
from ontology_platform.modules.connectors.errors import InvalidValueError
from ontology_platform.modules.connectors.schemas import CatalogColumn


def source_mismatch() -> AppError:
    return AppError(409, "query.source_mismatch", "The data source does not match the binding.")


def source_disabled() -> AppError:
    return AppError(409, "query.source_disabled", "The data source is disabled.")


def object_not_found() -> AppError:
    return AppError(404, "query.object_not_found", "The object was not found.")


def invalid_cursor() -> AppError:
    return AppError(422, "query.invalid_cursor", "The cursor is invalid for this request.")


def sort_value_too_long() -> AppError:
    return AppError(
        422, "query.sort_value_too_long", "A sort value is too long to continue to the next page."
    )


def invalid_value(
    exc: InvalidValueError, key_specs: Sequence[CatalogColumn], filtered: bool
) -> AppError:
    if not key_specs:
        if filtered:
            return AppError(422, "query.invalid_filter", "The filter is invalid.")
        return source_mismatch()
    if exc.column is not None:
        return (
            object_not_found()
            if any(c.name == exc.column for c in key_specs)
            else source_mismatch()
        )
    # The database alone knows the enum labels. For an already parsed UUID, integer or date,
    # an invalid textual representation instead points to an expression in the source.
    match exc.sqlstate:
        case "22P02":
            key_rejected = any(c.family == "opaque" and c.type.lower() != "uuid" for c in key_specs)
        case "22003":
            key_rejected = any(c.family == "decimal" for c in key_specs)
        case "22007" | "22008":
            key_rejected = any(c.family == "dateTime" for c in key_specs)
        case _:
            key_rejected = exc.sqlstate is None
    return object_not_found() if key_rejected else source_mismatch()
