"""Instructions and structured-output schemas for the staged extraction (spec 001 §4).

Prompts are in English (models follow them best) but ask for labels in the source language.
Every schema field is required (nullable where optional) so that strict structured outputs work.
"""

from typing import Literal

from pydantic import BaseModel, Field

COMMON_RULES = """\
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
{COMMON_RULES}"""

TYPES_INSTRUCTIONS = f"""\
You are an ontology engineer. From the candidate terms below, decide which are entity types
(classes of business objects or events that have their own identity), and arrange them into a
shallow hierarchy only where the text supports an "is a kind of" relation.
Existing entity types are listed with their ids; reuse them instead of proposing duplicates
(refer to an existing type by its id). For each new type, choose a PascalCase English
local_name and refer to it as "new:<local_name>". Attributes, values and relations are not
entity types.
{COMMON_RULES}"""

RELATIONS_INSTRUCTIONS = f"""\
You are an ontology engineer. Using only the entity types listed (refer to them by their ref),
find in the text (1) relations between two entity types and (2) attributes of an entity type.
Give relations and attributes a camelCase English local_name. For attributes choose the
datatype and the unit symbol when the text states one (for example mm, t, ℃, %, MPa, m/min).
"required" means every instance must have it; "multiple" means an instance can have several.
{COMMON_RULES}"""


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
    ref: str = Field(description='Existing type id, or "new:<local_name>" for a new type')
    label_zh: str
    label_en: str | None
    local_name: str
    definition_zh: str | None
    synonyms: list[str]
    parent: str | None = Field(description="ref of the parent type, if the text supports one")
    confidence: float
    rationale: str
    quotes: list[Quote]


class TypesOut(BaseModel):
    entity_types: list[EntityTypeOut]


class RelationOut(BaseModel):
    label_zh: str
    label_en: str | None
    local_name: str
    domain: str
    range: str
    required: bool
    multiple: bool
    definition_zh: str | None
    confidence: float
    rationale: str
    quotes: list[Quote]


class PropertyOut(BaseModel):
    label_zh: str
    label_en: str | None
    local_name: str
    domain: str
    datatype: Literal["string", "integer", "decimal", "boolean", "date", "dateTime"]
    unit: str | None
    required: bool
    multiple: bool
    definition_zh: str | None
    confidence: float
    rationale: str
    quotes: list[Quote]


class RelationsOut(BaseModel):
    relations: list[RelationOut]
    properties: list[PropertyOut]


TRANSCRIBE_INSTRUCTIONS = """\
You transcribe a scanned document so that it can be searched and quoted. Copy the text of every
page exactly as printed, in reading order, without summarising, translating or correcting it.
Render tables as one row per line with cells separated by " | ". Give each page's number and,
when the page starts with a section heading, that heading. Skip pages that have no text.
"""


class PageOut(BaseModel):
    number: int = Field(description="1-based page number in the file")
    heading: str | None
    text: str


class TranscriptOut(BaseModel):
    pages: list[PageOut]
