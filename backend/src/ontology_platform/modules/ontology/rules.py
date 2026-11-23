"""Naming and per-kind field rules shared by review, merge and publish."""

import re
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from pydantic.alias_generators import to_camel

from ontology_platform.modules.ontology.schemas import ElementFields, Synonym

LOCAL_NAME = re.compile(r"[A-Za-z][A-Za-z0-9]*")
LOCAL_NAME_MAX_LENGTH = 128

REF_FIELDS = ("parent_ref", "domain_ref", "range_ref")
# Reference fields each kind uses, and which of them are mandatory.
KIND_REFS: dict[str, tuple[str, ...]] = {
    "entity_type": ("parent_ref",),
    "relation_type": ("domain_ref", "range_ref"),
    "property": ("domain_ref",),
}
REQUIRED_REFS: dict[str, tuple[str, ...]] = {
    "entity_type": (),
    "relation_type": ("domain_ref", "range_ref"),
    "property": ("domain_ref",),
}


def wire_name(field: str) -> str:
    """The camelCase name of an ElementFields field, for messages."""
    return to_camel(field)


def local_name_problem(kind: str, local_name: str) -> str | None:
    """Object types are PascalCase, relations and properties camelCase."""
    if len(local_name) > LOCAL_NAME_MAX_LENGTH or not LOCAL_NAME.fullmatch(local_name):
        return "localName must start with a letter and contain only letters and digits"
    if kind == "entity_type" and not local_name[0].isupper():
        return "localName of an object type must be PascalCase"
    if kind != "entity_type" and not local_name[0].islower():
        return "localName of a relation or property must be camelCase"
    return None


def parse_id(ref: str) -> UUID | None:
    """The element id a reference holds, or None when it is a temp_ref."""
    try:
        return UUID(ref)
    except ValueError:
        return None


def is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


def field_problems(
    kind: str,
    op: str,
    fields: ElementFields,
    *,
    target_local_name: str | None = None,
) -> list[str]:
    """Problems with the shape of effective item fields that need no database lookups.

    For `create` the fields must describe a complete element. For `update` only the given keys
    are checked; the local name cannot change and mandatory values cannot be cleared.
    """
    given = fields.model_fields_set
    problems: list[str] = []
    for name in REF_FIELDS:
        if name not in KIND_REFS[kind] and getattr(fields, name) is not None:
            problems.append(f"{wire_name(name)} does not apply to {kind}")
    if kind != "property":
        if fields.datatype is not None:
            problems.append(f"datatype does not apply to {kind}")
        if fields.unit is not None:
            problems.append(f"unit does not apply to {kind}")

    if op == "create":
        if fields.local_name is None:
            problems.append("localName is required")
        else:
            problem = local_name_problem(kind, fields.local_name)
            if problem:
                problems.append(problem)
        if is_blank(fields.label_zh):
            problems.append("labelZh is required")
        problems.extend(
            f"{wire_name(name)} is required"
            for name in REQUIRED_REFS[kind]
            if getattr(fields, name) is None
        )
        if kind == "property" and fields.datatype is None:
            problems.append("datatype is required")
        return problems

    if "local_name" in given and fields.local_name != target_local_name:
        problems.append("localName cannot change")
    if "label_zh" in given and is_blank(fields.label_zh):
        problems.append("labelZh is required")
    problems.extend(
        f"{wire_name(name)} is required"
        for name in REQUIRED_REFS[kind]
        if name in given and getattr(fields, name) is None
    )
    if kind == "property" and "datatype" in given and fields.datatype is None:
        problems.append("datatype is required")
    return problems


def effective_fields(proposed: dict[str, Any], edited: dict[str, Any] | None) -> ElementFields:
    """The fields a merge applies: the proposal, overridden key by key by the reviewer's edit."""
    return ElementFields.model_validate({**proposed, **(edited or {})})


def stored_fields(fields: ElementFields) -> dict[str, Any]:
    """JSON for change_items.proposed / edited: camelCase, only the keys that were given."""
    return fields.model_dump(mode="json", by_alias=True, exclude_unset=True)


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def merge_synonyms(*groups: Iterable[Synonym | dict[str, Any]]) -> list[dict[str, Any]]:
    """Concatenate synonym lists, dropping blanks and case-insensitive duplicates per language."""
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for entry in group:
            synonym = entry if isinstance(entry, Synonym) else Synonym.model_validate(entry)
            text = synonym.text.strip()
            key = (synonym.lang, text.casefold())
            if not text or key in seen:
                continue
            seen.add(key)
            merged.append({"lang": synonym.lang, "text": text})
    return merged
