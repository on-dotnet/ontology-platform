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
- Sentences are numbered like [3.12] (chunk 3, sentence 12). Cite evidence by number, for
  example "3.12"; never copy text. Use null when no sentence supports an item.
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

# One reading of "a thing and the record of it" for the types and resolve stages (#57, #58):
# the two stages used to answer it in opposite ways. Examples come from other fields than the
# case packs, so that the evaluation is not flattered.
RECORD_RULE = """\
A thing and the record of it are one concept unless the record is identified and kept track of
on its own. An event known only through its record (every occurrence is one record) is one
concept with the record, named by the record, even when the record has a number: the number
identifies the occurrence ("hospital admission" and "admission record"). Master data kept for
each thing under the thing's own number is the thing ("customer" and "customer master
record"). A record with an identity of its own, different from the thing's, is a different
concept ("patient" and "insurance card").
"""

TYPES_INSTRUCTIONS = f"""\
You are an ontology engineer. From the candidate terms below, decide which are entity types
(classes of business objects or events that have their own identity), and arrange them into a
shallow hierarchy only where the text supports an "is a kind of" relation.
An entity type is a class whose members are identified and kept track of one by one: usually
each has a number or code of its own, or the text lists the data recorded for every single one
(for example "every loan is recorded with the borrower and the due date"). A number is the
most common evidence, not the only one. Such members are physical things (equipment,
containers, materials and products), events that the text treats as occurrences in their own
right, and records, documents and plans of which every single one is kept track of (a
consignment note; a timetable whose lines each name a train).
These are not entity types:
- Process steps, operations and activities, whether named by a verb or by an action noun (for
  example unpacking, sealing, cleaning, labelling, auditing). When the text writes the data of
  each occurrence on a document of another kind (a ticket, a consignment note), propose that
  document, not the activity. An event that the text defines as an occurrence and records
  each time, with what it concerns, who and when, stays a type even without a number of its
  own.
- Outcomes, statuses, the possible values of a decision, quality levels and other categories
  (these are values). A kind of activity or record told apart only by its level, frequency or
  result (daily and weekly rounds) is a value of an attribute, not a type of its own. Results
  that are recorded one by one, each with its own measured value, the time it was obtained and
  the item it was measured on (every reading of a lab test), are records, not values.
- Measurable quantities (attributes).
- People, roles and departments mentioned only as the one who acts; a role that an existing
  kind of thing plays (a preferred carrier, a guarantor who is also a customer); places such
  as a ward or a reading room that the text names only as where something happens.
- Parts, points and zones of equipment and input materials, even when a standard or plan
  refers to them, unless each one is identified and kept track of on its own. Lines or items
  of a plan, list or standard (a checklist item, a step of a procedure) are part of the
  document that contains them, except a line that has a line number of its own and that other
  records refer to line by line (an invoice line that every credit note cites by its number):
  such a line is an entity type.
- Slips, copies, receipts, tags, labels and attachments that go with a thing or confirm a
  handover (a delivery receipt, a luggage tag), unless each one has a number of its own and is
  kept track of on its own; what they record belongs to the thing or event they go with.
- Registers, ledgers, directories, lists, tables, statistics, charts and analysis reports that
  collect or summarise entries about other things (a price list, a list of members, a weekly
  summary); propose the things they list instead. A table that says which documents are kept,
  by whom and for how long does not make each document it names a type.
- Requests, applications, permits and notifications that are not kept track of one by one;
  what they ask for or record belongs, as attributes, to the object they concern.
One concept is one type. When several terms name the same thing (a short and a qualified
name), propose one type, name it by the general term the text uses most, and put the other
names in synonyms. Plans, reports or records that differ only by period or frequency (a
weekly and a monthly timetable) are one type; the period is an attribute.
{RECORD_RULE}A process and the equipment that performs it are different concepts; keep the
equipment, and the process only if it is an event as defined above.
Before proposing a new type, check that the text shows how each member is identified (a number
or code of its own) or that the data of every single one is recorded. Being mentioned, kept,
handed over or referred to is not enough.
Existing entity types are listed with short ids (E1, E2, ...); reuse them instead of proposing
duplicates (refer to an existing type by its id). Refer to a new type as "new:<Name>", where
<Name> is a PascalCase English name. Give a concise English label, and a definition of one
sentence, or null. Attributes, values and relations are not entity types.
Each term is shown with the sentences it was found in; cite the one sentence that best shows
the type.
{COMMON_RULES}{CITE_RULE}"""

RELATIONS_INSTRUCTIONS = f"""\
You are an ontology engineer. Using only the entity types listed (refer to them by their ref),
find in the text (1) relations between two entity types and (2) attributes of an entity type.
Propose a relation only where the text states the link directly and names both types (by their
label or a synonym). Usually one sentence, list item or table row does; cite it. Where it takes
a few units together to state the link, such as an introducing sentence and its list items or a
table header and the row right after it, cite that run instead, as the first and last number
of at most three consecutive sentences of one chunk, for example "3.12-3.14". Relations whose
cited sentences do not name both types are discarded; an attribute cites one sentence. Do not
derive relations from the order of process steps, from shared attributes or from general
knowledge, and give each link once, in one direction. Give relations and attributes a
camelCase English local_name. Give a definition only where the text defines the relation or
attribute; otherwise null. For attributes choose the datatype and the unit symbol when the
text states one (for example mm, t, ℃, %, MPa, m/min). "required" means every instance must
have it; "multiple" means an instance can have several.
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


RESOLVE_INSTRUCTIONS = f"""\
You are an ontology engineer. Each object type below was just identified in a document and is
listed with its candidates: types it might be the same as (existing ones, types proposed by
other documents, or types of this document). For each type, decide whether one of its
candidates is the same concept.
Same concept means the same kind of thing under another name: an abbreviation, a fuller name,
a synonym or a name used by another department (for example "car" and "automobile", or
"invoice" and "bill"). These are not the same concept: a kind of something and that something
("sports car" and "car"), a whole and its parts ("car" and "engine"), a process and the
equipment that performs it ("painting" and "paint booth"), and two kinds of one thing that
share a general name.
{RECORD_RULE}Answer per type, in one line: "same" with the candidate it is; "different" with
candidate null when no candidate is the same concept; "unsure" with the candidate it may be
when the names, definitions and context are not enough to tell. Do not guess: answer unsure
instead.
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
