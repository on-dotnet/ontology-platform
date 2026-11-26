"""Naming and per-kind field rules shared by review, merge and publish."""

import re
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from pydantic.alias_generators import to_camel

from ontology_platform.modules.ontology import binding_rules
from ontology_platform.modules.ontology.models import BINDING_KINDS
from ontology_platform.modules.ontology.schemas import ElementFields, Synonym

LOCAL_NAME = re.compile(r"[A-Za-z][A-Za-z0-9]*")
LOCAL_NAME_MAX_LENGTH = 128

REF_FIELDS = ("parent_ref", "domain_ref", "range_ref", "inverse_ref", "subject_ref")
# Reference fields each kind uses.
KIND_REFS: dict[str, tuple[str, ...]] = {
    "entity_type": ("parent_ref",),
    "relation_type": ("domain_ref", "range_ref", "inverse_ref"),
    "property": ("domain_ref",),
    "constraint": ("domain_ref",),
    "axiom": (),
    "metric": ("subject_ref",),
    **binding_rules.REFS,
}
# Mandatory references of elements made in the platform. Imported elements (explicit IRI) may
# lack them, as OWL allows (spec 002, 3.1); a constraint always needs its target type.
REQUIRED_REFS: dict[str, tuple[str, ...]] = {
    "entity_type": (),
    "relation_type": ("domain_ref", "range_ref"),
    "property": ("domain_ref",),
    "constraint": ("domain_ref",),
    "axiom": (),
    "metric": ("subject_ref",),
    **binding_rules.REFS,
}
# The kinds each reference of a semantic element may point at; see `ref_targets`.
REF_TARGETS: dict[str, tuple[str, ...]] = {
    "parent_ref": ("entity_type",),
    "domain_ref": ("entity_type",),
    "range_ref": ("entity_type",),
    "inverse_ref": ("relation_type",),
    "subject_ref": ("entity_type",),
}
RULE_PATH_KINDS = ("relation_type", "property")
_PASCAL_KINDS = ("entity_type", "constraint")
_MEMBER_FIELDS = ("required", "multiple")


def ref_targets(kind: str, name: str) -> tuple[str, ...]:
    """The kinds reference `name` of an element of `kind` may point at: a binding's parent,
    domain and range are type bindings, its subject depends on the kind (spec 003, 6.2)."""
    return binding_rules.REF_TARGETS.get((kind, name)) or REF_TARGETS[name]


def wire_name(field: str) -> str:
    """The camelCase name of an ElementFields field, for messages."""
    return to_camel(field)


def local_name_problem(kind: str, local_name: str, *, imported: bool = False) -> str | None:
    """Object types and constraints are PascalCase, relations, properties and metrics camelCase.

    Local names of imported elements only identify them in the platform (their IRI comes with
    the file), so the case conventions do not apply to them.
    """
    if len(local_name) > LOCAL_NAME_MAX_LENGTH or not LOCAL_NAME.fullmatch(local_name):
        return "localName must start with a letter and contain only letters and digits"
    if imported:
        return None
    if kind in _PASCAL_KINDS and not local_name[0].isupper():
        return "localName of an object type or constraint must be PascalCase"
    if kind not in _PASCAL_KINDS and not local_name[0].islower():
        return "localName of a relation, property or metric must be camelCase"
    return None


def display_label(label_zh: str | None, label_en: str | None, local_name: str | None) -> str:
    """What the platform shows as an element's name (spec 002, 3.1)."""
    return label_zh or label_en or local_name or ""


def parse_id(ref: str) -> UUID | None:
    """The element id a reference holds, or None when it is a temp_ref."""
    try:
        return UUID(ref)
    except ValueError:
        return None


def is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _kind_problems(kind: str, fields: ElementFields) -> list[str]:
    """Fields given that the kind does not have."""
    problems: list[str] = []
    for name in REF_FIELDS:
        if name not in KIND_REFS[kind] and getattr(fields, name) is not None:
            problems.append(f"{wire_name(name)} does not apply to {kind}")
    checks = [
        ("datatype", kind == "property"),
        ("unit", kind in ("property", "metric")),
        ("metric", kind == "metric"),
        *((name, kind in RULE_PATH_KINDS) for name in _MEMBER_FIELDS),
        ("auto_shape", kind in ("entity_type", *RULE_PATH_KINDS)),
        ("rules", kind == "constraint"),
        ("turtle", kind == "axiom"),
        ("binding", kind in BINDING_KINDS),
    ]
    for name, applies in checks:
        if not applies and getattr(fields, name) is not None:
            problems.append(f"{wire_name(name)} does not apply to {kind}")
    if kind == "axiom" or kind in BINDING_KINDS:
        for name in (
            "local_name",
            "iri",
            "label_zh",
            "label_en",
            "definition_zh",
            "definition_en",
            "synonyms",
        ):
            if getattr(fields, name) is not None:
                problems.append(f"{wire_name(name)} does not apply to {kind}")
    return problems


def field_problems(
    kind: str,
    op: str,
    fields: ElementFields,
    *,
    target_local_name: str | None = None,
    target_imported: bool = False,
    target_binding: dict[str, Any] | None = None,
) -> list[str]:
    """Problems with the shape of effective item fields that need no database lookups.

    For `create` the fields must describe a complete element; an imported element (one with an
    explicit `iri`) may lack the Chinese label, references and datatype OWL does not require.
    For `update` and `restore` only the given keys are checked; the local name and IRI cannot
    change and mandatory values cannot be cleared. A `delete` carries no fields. Bindings
    follow `binding_rules.shape_problems`; `target_binding` is the binding an update changes.
    """
    given = fields.model_fields_set
    if op == "delete":
        return ["a delete item has no fields"] if given else []
    problems = _kind_problems(kind, fields)
    if kind in BINDING_KINDS:
        return problems + binding_rules.shape_problems(kind, op, fields, target_binding)

    if op == "create":
        if kind == "axiom":
            if is_blank(fields.turtle):
                problems.append("turtle is required")
            return problems
        imported = fields.iri is not None and kind != "metric"
        if kind == "metric" and fields.iri is not None:
            problems.append("iri is set by imports only")
        if fields.local_name is None:
            problems.append("localName is required")
        else:
            problem = local_name_problem(kind, fields.local_name, imported=imported)
            if problem:
                problems.append(problem)
        if not imported and is_blank(fields.label_zh):
            problems.append("labelZh is required")
        problems.extend(
            f"{wire_name(name)} is required"
            for name in REQUIRED_REFS[kind]
            if getattr(fields, name) is None and (not imported or kind in ("constraint", "metric"))
        )
        if kind == "property" and fields.datatype is None and not imported:
            problems.append("datatype is required")
        if kind == "constraint" and fields.rules is None:
            problems.append("rules is required")
        if kind == "metric" and fields.metric is None:
            problems.append("metric is required")
        return problems

    if "local_name" in given and fields.local_name != target_local_name:
        problems.append("localName cannot change")
    if "iri" in given:
        problems.append("iri cannot change")
    if kind == "axiom" and "turtle" in given and is_blank(fields.turtle):
        problems.append("turtle is required")
    label_required = not target_imported or kind == "metric"
    if "label_zh" in given and is_blank(fields.label_zh) and label_required:
        problems.append("labelZh is required")
    problems.extend(
        f"{wire_name(name)} is required"
        for name in REQUIRED_REFS[kind]
        if name in given
        and getattr(fields, name) is None
        and (not target_imported or kind in ("constraint", "metric"))
    )
    clears_datatype = "datatype" in given and fields.datatype is None
    if kind == "property" and clears_datatype and not target_imported:
        problems.append("datatype is required")
    if kind == "constraint" and "rules" in given and fields.rules is None:
        problems.append("rules is required")
    if kind == "metric" and "metric" in given and fields.metric is None:
        problems.append("metric is required")
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
