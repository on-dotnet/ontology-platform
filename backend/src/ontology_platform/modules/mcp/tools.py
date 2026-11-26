"""The MCP tools (spec 003, 9.3): names, input schemas and handlers, independent of the
transport. The read tools read the release in effect; the one tool that writes, propose_changes
(9.4), only ever makes a change set waiting for review, through `ontology.assistant.propose`.

Ontology tools read semantic elements and metrics from the same immutable release. Their
results never name a table or a column. Object tools hand over to the query service and return
exactly what `/api` returns. Every call is audited as `mcp.tool_called`: the tool, the token,
the ontology and the result code, never the arguments (they hold filter values).
"""

import base64
import binascii
import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import chain
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.identity.models import TokenScope
from ontology_platform.modules.identity.tokens import TokenContext
from ontology_platform.modules.ontology import assistant, bindings, releases, rules
from ontology_platform.modules.ontology import service as ontology
from ontology_platform.modules.ontology.models import Datatype
from ontology_platform.modules.ontology.schemas import ElementCopy, ElementFields, ProposedItem
from ontology_platform.modules.query import schemas as query_schemas
from ontology_platform.modules.query import service as query
from ontology_platform.schemas import CamelModel

# A single tool result above this size is cut short (spec 003, 9.3).
RESULT_LIMIT_BYTES = 256 * 1024
ELEMENT_KINDS = ("entity_type", "relation_type", "property", "constraint", "metric")
ELEMENTS_DEFAULT = 20
ELEMENTS_MAX = 100

type ElementKind = Literal["entity_type", "relation_type", "property", "constraint", "metric"]
Ref = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ToolError(Exception):
    """A tool failure reported as a result with `isError` (not a protocol error)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UnknownToolError(Exception):
    pass


@dataclass
class Context:
    db: AsyncSession
    request: Request
    token: TokenContext
    # Set once the ontology argument is resolved, for the audit.
    ontology_id: UUID | None = None


# ---------- arguments ----------


class Arguments(CamelModel):
    model_config = ConfigDict(extra="forbid")


class OntologyArguments(Arguments):
    ontology: Ref = Field(description="The ontology's id or key.")


class NoArguments(Arguments):
    pass


class SearchElementsArguments(OntologyArguments):
    query: str | None = Field(
        default=None,
        max_length=200,
        description="Matched against names, synonyms, definitions and local names.",
    )
    kinds: list[ElementKind] | None = Field(default=None, max_length=len(ELEMENT_KINDS))
    limit: int = Field(default=ELEMENTS_DEFAULT, ge=1, le=ELEMENTS_MAX)
    cursor: str | None = Field(default=None, max_length=500)


class GetElementArguments(OntologyArguments):
    id: Ref | None = Field(default=None, description="The element's id or local name.")
    iri: Ref | None = None

    @model_validator(mode="after")
    def one_reference(self) -> "GetElementArguments":
        if (self.id is None) == (self.iri is None):
            raise ValueError("give either id or iri")
        return self


class FilterArgument(Arguments):
    property_id: Ref = Field(description="The property's id, IRI or local name.")
    op: str
    value: Any = None


class SortArgument(Arguments):
    property_id: Ref = Field(description="The property's id, IRI or local name.")
    direction: Literal["asc", "desc"] = "asc"


class SearchObjectsArguments(OntologyArguments):
    type: Ref = Field(description="The object type's id, IRI or local name.")
    filters: list[FilterArgument] = Field(
        default_factory=list, max_length=query_schemas.FILTERS_MAX
    )
    sort: list[SortArgument] = Field(default_factory=list, max_length=query_schemas.SORT_MAX)
    limit: int = Field(default=query_schemas.PAGE_DEFAULT, ge=1, le=query_schemas.PAGE_MAX)
    cursor: query_schemas.Cursor | None = None


class GetObjectArguments(OntologyArguments):
    type: Ref = Field(description="The object type's id, IRI or local name.")
    key: str = Field(min_length=1, max_length=query_schemas.KEY_MAX_LENGTH)


class GetRelatedObjectsArguments(GetObjectArguments):
    relation: Ref = Field(description="The relation's id, IRI or local name.")
    direction: query_schemas.Direction = "out"
    limit: int = Field(default=query_schemas.PAGE_DEFAULT, ge=1, le=query_schemas.PAGE_MAX)
    cursor: query_schemas.Cursor | None = None


# ---------- the released ontology ----------


async def _released(ctx: Context, reference: str) -> bindings.ReleasedOntology:
    released = await bindings.released_ontology(ctx.db, reference)
    if released is not None:
        ctx.ontology_id = released.ontology_id
        return released
    match = next(
        (
            summary
            for summary in await ontology.list_ontologies(ctx.db)
            if reference in (str(summary.id), summary.key)
        ),
        None,
    )
    if match is None:
        raise AppError(404, "ontology.not_found", "Ontology not found.")
    ctx.ontology_id = match.id
    raise AppError(409, "query.no_release", "The ontology has no active release.")


def _element(
    released: bindings.ReleasedOntology,
    reference: str,
    kinds: Iterable[str],
    *,
    iri: bool = True,
    metrics: Sequence[releases.MetricElement] = (),
) -> ElementCopy | None:
    """An element of one of `kinds` by id, IRI or local name."""
    wanted = set(kinds)
    candidates = [e for e in chain(released.elements, metrics) if e.kind in wanted]
    for matches in (
        lambda e: str(e.id) == reference,
        lambda e: iri and e.iri == reference,
        lambda e: e.local_name == reference,
    ):
        found = next((element for element in candidates if matches(element)), None)
        if found is not None:
            return found
    return None


def _element_not_found() -> AppError:
    return AppError(404, "element.not_found", "Element not found.")


def _name(element_id: UUID | None, by_id: Mapping[UUID, ElementCopy]) -> str | None:
    other = by_id.get(element_id) if element_id is not None else None
    return _label(other) if other is not None else None


def _label(element: ElementCopy) -> str:
    return rules.display_label(element.label_zh, element.label_en, element.local_name)


def _brief(element: ElementCopy, by_id: Mapping[UUID, ElementCopy]) -> dict[str, Any]:
    return {
        "id": str(element.id),
        "kind": element.kind,
        "iri": element.iri,
        "labelZh": element.label_zh,
        "labelEn": element.label_en,
        "definitionZh": element.definition_zh,
        "definitionEn": element.definition_en,
        "synonyms": [{"lang": s.lang, "text": s.text} for s in element.synonyms],
        "parent": _name(element.parent_id, by_id),
        "domain": _name(element.domain_id, by_id),
        "range": _name(element.range_id, by_id),
        "inverse": _name(element.inverse_id, by_id),
        "datatype": element.datatype,
        "unit": element.unit,
    }


def _release(released: bindings.ReleasedOntology) -> dict[str, Any]:
    return {"id": str(released.release_id), "version": released.version}


async def _metrics(
    ctx: Context, released: bindings.ReleasedOntology
) -> tuple[releases.MetricElement, ...]:
    # Reading the active release a second time could mix snapshots during activation.
    _, metrics = await releases.metric_elements(
        ctx.db, released.ontology_id, release_id=released.release_id
    )
    return metrics


def _order(element: ElementCopy) -> tuple[int, str, str]:
    return (ELEMENT_KINDS.index(element.kind), _label(element), str(element.id))


def _matches(element: ElementCopy, needle: str) -> bool:
    texts = [
        element.label_zh,
        element.label_en,
        element.local_name,
        element.definition_zh,
        element.definition_en,
        *(synonym.text for synonym in element.synonyms),
    ]
    return any(needle in text.casefold() for text in texts if text)


def _encode_cursor(payload: list[Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> list[Any]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, binascii.Error):
        payload = None
    if (
        not isinstance(payload, list)
        or len(payload) != 3
        or not all(isinstance(part, str) for part in payload[:2])
        or type(payload[2]) is not int
        or payload[2] < 0
    ):
        raise AppError(422, "query.invalid_cursor", "The cursor does not match the request.")
    return payload


async def list_ontologies(ctx: Context, arguments: NoArguments) -> dict[str, Any]:
    items = []
    for summary in await ontology.list_ontologies(ctx.db):
        if summary.active_release_id is None:
            continue
        release = await releases.get_release(ctx.db, summary.active_release_id)
        items.append(
            {
                "id": str(summary.id),
                "key": summary.key,
                "name": summary.name,
                "description": summary.description,
                "releaseId": str(release.id),
                "version": release.version,
                "publishedAt": release.created_at.isoformat(),
            }
        )
    return {"ontologies": items}


async def search_elements(ctx: Context, arguments: SearchElementsArguments) -> dict[str, Any]:
    released = await _released(ctx, arguments.ontology)
    needle = (arguments.query or "").strip().casefold()
    kinds = sorted(set(arguments.kinds or ELEMENT_KINDS))
    # The cursor is tied to the release and to the question, so a changed one is noticed.
    question = hashlib.sha256(json.dumps([needle, kinds]).encode()).hexdigest()[:16]
    offset = 0
    if arguments.cursor is not None:
        release_id, asked, offset = _decode_cursor(arguments.cursor)
        if asked != question:
            raise AppError(422, "query.invalid_cursor", "The cursor does not match the request.")
        if release_id != str(released.release_id):
            raise AppError(409, "query.release_changed", "The active release has changed.")
    metrics = await _metrics(ctx, released) if "metric" in kinds else ()
    found = sorted(
        (
            element
            for element in chain(released.elements, metrics)
            if element.kind in kinds and (not needle or _matches(element, needle))
        ),
        key=_order,
    )
    by_id = {element.id: element for element in released.elements}
    page = found[offset : offset + arguments.limit]
    following = offset + len(page)
    return {
        "release": _release(released),
        "items": [_brief(element, by_id) for element in page],
        "nextCursor": (
            _encode_cursor([str(released.release_id), question, following])
            if following < len(found)
            else None
        ),
    }


def _lineage(element: ElementCopy, by_id: Mapping[UUID, ElementCopy]) -> list[UUID]:
    """The type and its ancestors, nearest first."""
    chain: list[UUID] = []
    current: ElementCopy | None = element
    while current is not None and current.id not in chain:
        chain.append(current.id)
        current = by_id.get(current.parent_id) if current.parent_id is not None else None
    return chain


def _of(
    elements: Sequence[ElementCopy], kind: str, attribute: str, lineage: Sequence[UUID]
) -> list[ElementCopy]:
    def rank(element: ElementCopy) -> tuple[int, str, str]:
        owner = cast(UUID, getattr(element, attribute))
        return (lineage.index(owner), _label(element), str(element.id))

    return sorted(
        (e for e in elements if e.kind == kind and getattr(e, attribute) in lineage), key=rank
    )


async def get_element(ctx: Context, arguments: GetElementArguments) -> dict[str, Any]:
    released = await _released(ctx, arguments.ontology)
    metrics = await _metrics(ctx, released)
    if arguments.iri is not None:
        found = next(
            (
                e
                for e in chain(released.elements, metrics)
                if e.kind in ELEMENT_KINDS and e.iri == arguments.iri
            ),
            None,
        )
    else:
        found = _element(
            released, cast(str, arguments.id), ELEMENT_KINDS, iri=False, metrics=metrics
        )
    if found is None:
        raise _element_not_found()
    elements = released.elements
    by_id = {element.id: element for element in elements}
    info: dict[str, Any] = {
        "release": _release(released),
        **_brief(found, by_id),
        "required": found.required,
        "multiple": found.multiple,
    }
    if found.kind == "constraint":
        info["rules"] = [rule.model_dump(mode="json", by_alias=True) for rule in found.rules or []]
    if isinstance(found, releases.MetricElement):
        info["metric"] = _dump(found.metric)
    if found.kind == "entity_type":
        lineage = _lineage(found, by_id)
        info["properties"] = [
            _brief(e, by_id) for e in _of(elements, "property", "domain_id", lineage)
        ]
        info["relationsOut"] = [
            _brief(e, by_id) for e in _of(elements, "relation_type", "domain_id", lineage)
        ]
        info["relationsIn"] = [
            _brief(e, by_id) for e in _of(elements, "relation_type", "range_id", lineage)
        ]
        info["children"] = [
            {"id": str(e.id), "label": _label(e)}
            for e in _of(elements, "entity_type", "parent_id", [found.id])
        ]
        info["constraints"] = [
            {"id": str(e.id), "label": _label(e), "ruleCount": len(e.rules or [])}
            for e in _of(elements, "constraint", "domain_id", [found.id])
        ]
        info["hasData"] = found.id in released.bound_type_ids
    return info


# ---------- objects ----------


def _dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True)


async def _type(ctx: Context, reference: str, type_: str) -> tuple[UUID, bindings.ReleasedOntology]:
    released = await _released(ctx, reference)
    found = _element(released, type_, ["entity_type"])
    if found is None:
        raise _element_not_found()
    return found.id, released


def _property(released: bindings.ReleasedOntology, reference: str) -> str:
    found = _element(released, reference, ["property"])
    if found is None:
        raise AppError(422, "query.invalid_filter", "The filter is invalid.")
    return str(found.id)


async def search_objects(ctx: Context, arguments: SearchObjectsArguments) -> dict[str, Any]:
    type_id, released = await _type(ctx, arguments.ontology, arguments.type)
    try:
        body = _object_search(type_id, released, arguments)
    except ValidationError as exc:
        # Arguments the tool accepted but the query service's own model refuses.
        raise _invalid(exc) from None
    page = await query.until_disconnected(
        ctx.request, query.search(ctx.db, released.ontology_id, body)
    )
    return _dump(page)


def _object_search(
    type_id: UUID, released: bindings.ReleasedOntology, arguments: SearchObjectsArguments
) -> query_schemas.ObjectSearch:
    return query_schemas.ObjectSearch.model_validate(
        {
            "typeId": type_id,
            "filters": [
                {"propertyId": _property(released, f.property_id), "op": f.op, "value": f.value}
                for f in arguments.filters
            ],
            "sort": [
                {"propertyId": _property(released, s.property_id), "direction": s.direction}
                for s in arguments.sort
            ],
            "limit": arguments.limit,
            "cursor": arguments.cursor,
        }
    )


async def get_object(ctx: Context, arguments: GetObjectArguments) -> dict[str, Any]:
    type_id, released = await _type(ctx, arguments.ontology, arguments.type)
    found = await query.until_disconnected(
        ctx.request, query.get_object(ctx.db, released.ontology_id, type_id, arguments.key)
    )
    return _dump(found)


async def get_related_objects(
    ctx: Context, arguments: GetRelatedObjectsArguments
) -> dict[str, Any]:
    type_id, released = await _type(ctx, arguments.ontology, arguments.type)
    relation = _element(released, arguments.relation, ["relation_type"])
    if relation is None:
        raise _element_not_found()
    page = await query.until_disconnected(
        ctx.request,
        query.related(
            ctx.db,
            released.ontology_id,
            type_id,
            arguments.key,
            relation_id=relation.id,
            direction=arguments.direction,
            limit=arguments.limit,
            cursor=arguments.cursor,
        ),
    )
    return _dump(page)


# ---------- proposing changes (spec 003, 9.4) ----------

# Per access token and hour, and open at a time per owner.
PROPOSALS_PER_HOUR = 10
OPEN_PROPOSALS_MAX = 20
OPERATIONS_MAX = 50
RATIONALE_MAX_LENGTH = 2000
PROPOSAL_TITLE_PREFIX = "MCP："
PROPOSAL_TITLE_LENGTH = 60

ElementRef = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
_REF = "An element id, or the tempRef of an element an earlier operation creates."


class ProposedFields(Arguments):
    """The fields an operation sets. Only the keys given are changed. null clears labelEn,
    definitionZh, definitionEn, unit, parent and inverse; a required value (localName, labelZh,
    domain, range, datatype, turtle) cannot be cleared, and null leaves the synonyms, required
    and multiple as they are."""

    local_name: str | None = Field(default=None, max_length=128)
    label_zh: str | None = Field(default=None, max_length=200)
    label_en: str | None = Field(default=None, max_length=200)
    definition_zh: str | None = Field(default=None, max_length=4000)
    definition_en: str | None = Field(default=None, max_length=4000)
    synonyms_zh: list[str] | None = Field(
        default=None, description="Added to the element's synonyms; the existing ones stay."
    )
    synonyms_en: list[str] | None = Field(
        default=None, description="Added to the element's synonyms; the existing ones stay."
    )
    parent: ElementRef | None = Field(default=None, description=_REF)
    domain: ElementRef | None = Field(default=None, description=_REF)
    range: ElementRef | None = Field(default=None, description=_REF)
    inverse: ElementRef | None = Field(default=None, description=_REF)
    datatype: Datatype | None = None
    unit: str | None = Field(default=None, max_length=32)
    required: bool | None = None
    multiple: bool | None = None
    turtle: str | None = Field(default=None, description="The Turtle fragment of an axiom.")


class ProposedOperation(Arguments):
    op: Literal["create", "update", "delete"]
    # Bindings come from a data source's catalog (ontology.binding_proposals), never from here;
    # constraints are edited in their form.
    kind: Literal["entity_type", "relation_type", "property", "axiom"]
    target: str | None = Field(
        default=None,
        max_length=100,
        description="The id of the element an update or delete changes.",
    )
    temp_ref: ElementRef | None = Field(
        default=None,
        description='For a create: "new:<localName>", for later operations to refer to.',
    )
    fields: ProposedFields = Field(default_factory=ProposedFields)
    rationale: str = Field(min_length=1, max_length=RATIONALE_MAX_LENGTH, description="Why.")


class ProposeChangesArguments(OntologyArguments):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ] = Field(description="What the change set is about.")
    operations: list[ProposedOperation] = Field(min_length=1, max_length=OPERATIONS_MAX)


_RENAMED = {
    "parent": "parent_ref",
    "domain": "domain_ref",
    "range": "range_ref",
    "inverse": "inverse_ref",
}
_SYNONYMS = {"synonyms_zh": "zh", "synonyms_en": "en"}


def _proposed_item(operation: ProposedOperation) -> ProposedItem | None:
    """The operation as an ontology change item; None when its fields do not make one."""
    given = operation.fields
    values: dict[str, Any] = {}
    if operation.op != "delete":
        for name in given.model_fields_set - _SYNONYMS.keys():
            values[_RENAMED.get(name, name)] = getattr(given, name)
        if given.model_fields_set & _SYNONYMS.keys():
            values["synonyms"] = [
                {"lang": lang, "text": text}
                for name, lang in _SYNONYMS.items()
                for text in getattr(given, name) or []
            ]
    creates = operation.op == "create"
    try:
        return ProposedItem(
            op=operation.op,
            kind=operation.kind,
            target_element_id=None if creates or not operation.target else UUID(operation.target),
            temp_ref=operation.temp_ref if creates else None,
            proposed=ElementFields.model_validate(values),
            rationale=operation.rationale,
        )
    except ValueError:  # a malformed id, or fields that do not validate
        return None


def _proposal_title(title: str) -> str:
    text = " ".join(title.split())
    if len(text) > PROPOSAL_TITLE_LENGTH:
        text = text[:PROPOSAL_TITLE_LENGTH] + "…"
    return PROPOSAL_TITLE_PREFIX + text


async def _working_ontology(ctx: Context, reference: str) -> UUID:
    match = next(
        (
            summary
            for summary in await ontology.list_ontologies(ctx.db)
            if reference in (str(summary.id), summary.key)
        ),
        None,
    )
    if match is None:
        raise AppError(404, "ontology.not_found", "Ontology not found.")
    ctx.ontology_id = match.id
    return match.id


def _lock_key(owner: UUID) -> int:
    # A transaction-level advisory lock per owner: a signed 64-bit key from the namespace and id.
    digest = hashlib.sha256(b"mcp.propose_changes:" + owner.bytes).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


async def propose_changes(ctx: Context, arguments: ProposeChangesArguments) -> dict[str, Any]:
    ontology_id = await _working_ontology(ctx, arguments.ontology)
    owner = ctx.token.principal.id
    # One owner's proposals one at a time, so that two calls cannot both pass the limits.
    await ctx.db.execute(select(func.pg_advisory_xact_lock(_lock_key(owner))))
    since = datetime.now(UTC) - timedelta(hours=1)
    if (
        await ontology.count_mcp_change_sets(ctx.db, ctx.token.token_id, since=since)
        >= PROPOSALS_PER_HOUR
        or await ontology.count_open_mcp_change_sets(ctx.db, owner) >= OPEN_PROPOSALS_MAX
    ):
        raise ToolError(
            "mcp.rate_limited",
            f"At most {PROPOSALS_PER_HOUR} change sets per token and hour, and "
            f"{OPEN_PROPOSALS_MAX} open ones per user; try again later.",
        )
    items = [_proposed_item(operation) for operation in arguments.operations]
    proposal = await assistant.propose(
        ctx.db,
        ontology_id,
        message=arguments.title,
        created_by=owner,
        items=[item for item in items if item is not None],
        source="mcp",
        title=_proposal_title(arguments.title),
        token_id=ctx.token.token_id,
    )
    dropped = proposal.dropped + items.count(None)
    content: dict[str, Any] = {
        "changeSetId": str(proposal.change_set_id) if proposal.change_set_id else None,
        "proposed": len(items) - dropped,
        "dropped": dropped,
    }
    if dropped:
        content["notice"] = (
            f"{dropped} of the {len(items)} operations failed the checks of a manual edit "
            "(fields, references, names in use) and were left out."
        )
    return content


# ---------- the tool list ----------

type Handler = Callable[[Context, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    scope: TokenScope
    arguments: type[Arguments]
    run: Handler
    # The list a result too large is cut along; None when it has none.
    items: str | None = "items"
    annotations: Mapping[str, Any] = field(
        default_factory=lambda: {"readOnlyHint": True, "openWorldHint": False}
    )

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.arguments.model_json_schema(by_alias=True),
            "annotations": {"title": self.title, **self.annotations},
        }


_RELEASE = "Reads the release in effect; results carry its version."
TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            "list_ontologies",
            "List ontologies",
            "The ontologies that have a release in effect.",
            "ontology:read",
            NoArguments,
            list_ontologies,
            items="ontologies",
        ),
        Tool(
            "search_elements",
            "Search ontology elements",
            "Find object types, properties, relations, constraints and metrics by name, synonym, "
            "definition or local name. Use it to look up terms. " + _RELEASE,
            "ontology:read",
            SearchElementsArguments,
            search_elements,
        ),
        Tool(
            "get_element",
            "Get an ontology element",
            "One element in full. For an object type: its properties (inherited included), "
            "relations in and out, constraints, subtypes and whether it is bound to data. "
            + _RELEASE,
            "ontology:read",
            GetElementArguments,
            get_element,
            items=None,
        ),
        Tool(
            "search_objects",
            "Search objects",
            "List the objects of a type from the bound data: filter, sort and page with the "
            "cursor. Each object names its source. " + _RELEASE,
            "objects:read",
            SearchObjectsArguments,
            search_objects,
        ),
        Tool(
            "get_object",
            "Get an object",
            "One object by type and key (the `key` of a search result), with the relations "
            "it can be followed along. " + _RELEASE,
            "objects:read",
            GetObjectArguments,
            get_object,
            items=None,
        ),
        Tool(
            "get_related_objects",
            "Get related objects",
            "Follow a relation one hop from an object, forwards (out) or backwards (in). "
            + _RELEASE,
            "objects:read",
            GetRelatedObjectsArguments,
            get_related_objects,
        ),
        Tool(
            "propose_changes",
            "Propose ontology changes",
            "Propose changes to an ontology's working version: create, edit or delete object "
            "types, relations, properties and advanced axioms, each with its reason. They become "
            "one change set that people review; nothing changes until they merge it. Operations "
            "that fail the checks of a manual edit are left out and counted; deletes take along "
            "what depends on them. Bindings to data cannot be proposed. At most "
            f"{PROPOSALS_PER_HOUR} change sets per token and hour, {OPEN_PROPOSALS_MAX} open "
            "per user.",
            "changes:propose",
            ProposeChangesArguments,
            propose_changes,
            items=None,
            annotations={
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        ),
    )
}


def definitions() -> list[dict[str, Any]]:
    return [tool.definition() for tool in TOOLS.values()]


# ---------- calling ----------


def _size(content: Mapping[str, Any]) -> int:
    return len(text(content).encode())


def text(content: Mapping[str, Any]) -> str:
    """The text block of a result: the structured content as JSON."""
    return json.dumps(content, ensure_ascii=False)


def _fit(content: dict[str, Any], items: str | None) -> dict[str, Any]:
    """The content, or the longest prefix of its list that keeps it under the limit."""
    if _size(content) <= RESULT_LIMIT_BYTES:
        return content
    listed = content.get(items) if items is not None else None
    if isinstance(listed, list):
        notice = (
            f"The result was cut at {RESULT_LIMIT_BYTES // 1024} KB. "
            "Narrow the query or lower the limit to see the rest."
        )

        def cut(count: int) -> dict[str, Any]:
            shorter = {**content, cast(str, items): listed[:count], "truncated": True}
            if "nextCursor" in content:
                shorter["nextCursor"] = None
            return {**shorter, "notice": notice}

        low, high = 0, len(listed)
        while low < high:
            middle = (low + high + 1) // 2
            if _size(cut(middle)) <= RESULT_LIMIT_BYTES:
                low = middle
            else:
                high = middle - 1
        if low > 0:
            return cut(low)
    raise ToolError(
        "mcp.result_too_large",
        f"The result is larger than {RESULT_LIMIT_BYTES // 1024} KB; narrow the request.",
    )


def _invalid(exc: ValidationError) -> ToolError:
    # Locations and messages only: the rejected input may hold filter values.
    problems = "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'arguments'}: {error['msg']}"
        for error in exc.errors(include_input=False, include_url=False)
    )
    return ToolError("validation.failed", f"Invalid arguments: {problems}")


@dataclass(frozen=True, slots=True)
class Outcome:
    content: dict[str, Any]
    is_error: bool


async def call(
    db: AsyncSession,
    request: Request,
    token: TokenContext,
    name: str,
    arguments: Mapping[str, Any],
    *,
    ip: str | None,
) -> Outcome:
    tool = TOOLS.get(name)
    if tool is None:
        raise UnknownToolError(name)
    ctx = Context(db, request, token)

    async def audited(code: str) -> None:
        audit.record(
            db,
            "mcp.tool_called",
            actor_id=token.principal.id,
            target_type="access_token",
            target_id=str(token.token_id),
            detail={
                "tool": tool.name,
                "tokenId": str(token.token_id),
                "ontology": str(ctx.ontology_id) if ctx.ontology_id is not None else None,
                "code": code,
            },
            ip=ip,
        )
        await db.commit()

    try:
        if tool.scope not in token.scopes:
            raise ToolError("auth.insufficient_scope", "The access token lacks a scope.")
        try:
            parsed = tool.arguments.model_validate(dict(arguments))
        except ValidationError as exc:
            raise _invalid(exc) from None
        content = await tool.run(ctx, parsed)
        outcome = Outcome(_fit(content, tool.items), is_error=False)
    except (AppError, ToolError) as exc:
        message = exc.detail if isinstance(exc, AppError) else exc.message
        # Whatever the failure left in the session must not reach the audit's commit.
        await db.rollback()
        await audited(exc.code)
        return Outcome({"code": exc.code, "message": message}, is_error=True)
    except Exception as exc:
        # A disconnect (499) or a fault still leaves its trace before it propagates.
        await db.rollback()
        disconnected = isinstance(exc, HTTPException) and exc.status_code == 499
        await audited("mcp.client_disconnected" if disconnected else "internal.error")
        raise
    await audited("ok")
    return outcome
