"""Instructions and structured-output schemas for the staged extraction (spec 001 §4, 004 §4).

Prompts are in English (models follow them best) but ask for labels in the source language.
Every schema field is required (nullable where optional) so that strict structured outputs work.
Outputs are kept short (spec 004, 7.2): the types and relations stages cite evidence by sentence
number instead of copying it, existing types go by short ids (E1, E2), and items carry no
rationale. The terms stage keeps its verbatim quotes (see TERMS_RULES).
"""

from typing import Literal

from pydantic import BaseModel, Field

COMMON_RULES = """\
Rules:
- Use only the text provided. Do not add knowledge that the text does not state or clearly imply.
- Write labels and definitions in the language of the text (Chinese text gives Chinese labels).
- When unsure, lower the confidence (0 to 1) instead of guessing.
"""

CITE_RULE = """\
- Sentences are numbered like [3.12] (chunk 3, sentence 12). Cite the one sentence that supports
  an item by its number, for example "3.12"; never copy text. Use null when none does.
"""

# The terms stage is not trimmed (spec 004, 7.2, PR 4): without definitions and quotes the model
# listed about twice as many terms, and the types stage made types of many of them. Its request
# stays exactly what it was before PR 4 (also no reasoning effort), so its recordings replay.
TERMS_RULES = """\
Rules:
- Use only the text provided. Do not add knowledge that the text does not state or clearly imply.
- Every quote must be copied verbatim from the text, 5 to 120 characters, and identify its chunk
  by the number in the [chunk N] marker that precedes it.
- Write labels and definitions in the language of the text (Chinese text gives Chinese labels)
  and also give a concise English label.
- When unsure, lower the confidence (0 to 1) instead of guessing.
"""

TERMS_INSTRUCTIONS = f"""\
You are an ontology engineer reading an industrial document. List the domain terms that a
business ontology for this domain would need: business objects and events (entity), their
measurable or descriptive attributes (attribute), links between objects (relation), and
enumerated values such as grades or categories (value). Skip generic words.
{TERMS_RULES}"""

TYPES_INSTRUCTIONS = f"""\
You are an ontology engineer. From the candidate terms below, decide which are entity types
(classes of business objects or events that have their own identity), and arrange them into a
shallow hierarchy only where the text supports an "is a kind of" relation.
An entity type is a class whose individual members are told apart and kept track of: physical
things (equipment, containers, materials and products), records and documents, and events that
the text treats as occurrences in their own right, each with an identifier or with data
recorded for it (for example "every delivery is recorded with its date and quantity").
These are not entity types:
- Process steps and operations, usually named by a verb (for example unpacking, sorting,
  sealing, starting a machine). Data recorded at a step belongs, as attributes, to the object
  or event it is recorded for. Make a step a type only when the text records each occurrence
  of it as a record of its own.
- Outcomes, statuses, the possible results of a decision, quality levels and other categories
  (these are values); measurable quantities (attributes); people, roles and departments
  mentioned only as the one who acts; parts or zones of equipment and input materials that have
  no data of their own.
One concept is one type. When several terms name the same thing (a short and a qualified name,
a thing and the record of it), propose one type, name it by the general term the text uses
most, and put the other names in synonyms. A process and the equipment that performs it are
different concepts; keep the equipment, and the process only if it is an event as defined
above.
Existing entity types are listed with short ids (E1, E2, ...); reuse them instead of proposing
duplicates (refer to an existing type by its id). Refer to a new type as "new:<Name>", where
<Name> is a PascalCase English name. Give a concise English label, and a definition of one
sentence, or null. Attributes, values and relations are not entity types.
Each term is shown with the sentences it was found in; cite the sentence that best shows the
type.
{COMMON_RULES}{CITE_RULE}"""

RELATIONS_INSTRUCTIONS = f"""\
You are an ontology engineer. Using only the entity types listed (refer to them by their ref),
find in the text (1) relations between two entity types and (2) attributes of an entity type.
Propose a relation only where the text states the link directly and names both types (by their
label or a synonym). Usually one sentence, list item or table row does; cite it. Where it takes
a few units together to state the link, such as an introducing sentence and its list items or a
table header and a row, cite that run instead, as the first and last number of at most three
consecutive sentences of one chunk, for example "3.12-3.14". Relations whose cited sentences do
not name both types are discarded; an attribute cites one sentence. Do not derive relations
from the order of process steps, from shared attributes or from general knowledge, and give
each link once, in one direction. Give relations and attributes a camelCase English
local_name. Give a definition only where the text defines the relation or attribute; otherwise
null. For attributes choose the datatype and the unit symbol when the text states one (for
example mm, t, ℃, %, MPa, m/min). "required" means every instance must have it; "multiple"
means an instance can have several.
{COMMON_RULES}{CITE_RULE}"""

_CITED = 'Number of the sentence cited, for example "3.12"; null if none'


class Quote(BaseModel):
    chunk: int = Field(description="Number N of the [chunk N] marker the quote comes from")
    text: str


class TermOut(BaseModel):
    name: str
    english: str | None
    definition: str | None
    category: Literal["entity", "attribute", "relation", "value", "other"]
    quotes: list[Quote]


class TermsOut(BaseModel):
    terms: list[TermOut]


class EntityTypeOut(BaseModel):
    ref: str = Field(description='Existing type id (E1, ...), or "new:<Name>" for a new type')
    label_zh: str
    label_en: str | None
    definition_zh: str | None
    synonyms: list[str]
    parent: str | None = Field(description="ref of the parent type, if the text supports one")
    confidence: float
    sentence: str | None = Field(description=_CITED)


class TypesOut(BaseModel):
    entity_types: list[EntityTypeOut]


class RelationOut(BaseModel):
    label_zh: str
    local_name: str
    domain: str
    range: str
    required: bool
    multiple: bool
    definition_zh: str | None
    confidence: float
    sentence: str | None = Field(
        description='Sentence cited, "3.12", or a run of at most three, "3.12-3.14"; null if none'
    )


class PropertyOut(BaseModel):
    label_zh: str
    local_name: str
    domain: str
    datatype: Literal["string", "integer", "decimal", "boolean", "date", "dateTime"]
    unit: str | None
    required: bool
    multiple: bool
    definition_zh: str | None
    confidence: float
    sentence: str | None = Field(description=_CITED)


class RelationsOut(BaseModel):
    relations: list[RelationOut]
    properties: list[PropertyOut]


RESOLVE_INSTRUCTIONS = """\
You are an ontology engineer. Each object type below was just identified in a document and is
listed with its candidates: types it might be the same as (existing ones, types proposed by
other documents, or types of this document). For each type, decide whether one of its
candidates is the same concept.
Same concept means the same kind of thing under another name: an abbreviation, a fuller name,
a synonym or a name used by another department (for example "car" and "automobile", or
"invoice" and "bill"). These are not the same concept: a kind of something and that something
("sports car" and "car"), a whole and its parts ("car" and "engine"), a process and the
equipment that performs it ("painting" and "paint booth"), a thing and the record of it
("shipment" and "shipping note"), and two kinds of one thing that share a general name.
Answer per type, in one line: "same" with the candidate it is; "different" with candidate null
when no candidate is the same concept; "unsure" with the candidate it may be when the names,
definitions and context are not enough to tell. Do not guess: answer unsure instead.
Give the reason in at most 30 characters, in the language of the names.
"""


class DecisionOut(BaseModel):
    type: str = Field(description="id of the type judged (T1, T2, ...)")
    candidate: str | None = Field(
        description='id of the candidate (C1, C2, ...); null when the verdict is "different"'
    )
    verdict: Literal["same", "different", "unsure"]
    reason: str


class ResolveOut(BaseModel):
    decisions: list[DecisionOut]


TRANSCRIBE_INSTRUCTIONS = """\
You transcribe a scanned document so that it can be searched and quoted. Copy the text of every
page exactly as printed, in reading order, without summarising, translating or correcting it.
Render tables as one row per line with cells separated by " | ". Give each page's number and,
when the page starts with a section heading, that heading. Number the pages of the attached file
from 1, ignoring any page numbers printed on them. Skip pages that have no text.
"""


class PageOut(BaseModel):
    number: int = Field(description="1-based position of the page in the attached file")
    heading: str | None
    text: str


class TranscriptOut(BaseModel):
    pages: list[PageOut]


# ---------- AI assistant (spec 002 §10) ----------

ASSISTANT_INSTRUCTIONS = """\
You are an ontology engineer helping a user who maintains an ontology. The user describes a
change in their own words; you propose operations that make exactly that change. A human
reviews every operation before anything changes.

Rules:
- Do only what the user asked. Do not tidy up, rename or extend anything else.
- Refer to existing elements by the id given in the element list. For a new element, choose a
  local_name (PascalCase for object types, camelCase for relations and properties) and refer to
  it in the same answer as "new:<local_name>"; put that ref in temp_ref.
- In fields, give only what the operation sets; every field you do not set must be null. To
  clear a parent, domain, range or inverse, write "none". Synonyms you give are added.
- Write labels in the language the user writes in (Chinese gives label_zh) and also give a
  concise English label for new elements.
- Constraints cannot be created or edited here, only deleted. Advanced axioms are Turtle
  fragments using the prefixes listed, one subject triple each.
- Deleting an element also removes what depends on it; the platform adds those changes itself.
- When unsure, lower the confidence (0 to 1) instead of guessing.
- If the request is a question, a data query or anything other than changing the ontology,
  return no operations and reply that this will be supported in a later version.
- If you cannot do what is asked, return no operations and say why in the reply.
- The reply is one or two short sentences in the user's language.
"""


class AssistantFieldsOut(BaseModel):
    label_zh: str | None
    label_en: str | None
    local_name: str | None
    definition_zh: str | None
    definition_en: str | None
    synonyms_zh: list[str] | None
    synonyms_en: list[str] | None
    parent: str | None = Field(description='ref of the parent type, or "none" to clear it')
    domain: str | None = Field(description='ref of the domain type, or "none" to clear it')
    range: str | None = Field(description='ref of the range type, or "none" to clear it')
    inverse: str | None = Field(description='ref of the inverse relation, or "none" to clear it')
    datatype: Literal["string", "integer", "decimal", "boolean", "date", "dateTime"] | None
    unit: str | None
    required: bool | None
    multiple: bool | None
    turtle: str | None = Field(description="Turtle fragment of an advanced axiom")


class AssistantOperationOut(BaseModel):
    op: Literal["create", "update", "delete"]
    kind: Literal["entity_type", "relation_type", "property", "constraint", "axiom"]
    target: str | None = Field(description="id of the element an update or delete changes")
    temp_ref: str | None = Field(description='"new:<local_name>" for a created element')
    fields: AssistantFieldsOut
    rationale: str
    confidence: float


class AssistantOut(BaseModel):
    reply: str
    operations: list[AssistantOperationOut]
