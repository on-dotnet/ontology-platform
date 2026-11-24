import type { AssistantRequest } from '@/features/assistant/api';
import type { DocumentInfo } from '@/features/documents/api';
import type { EditRequest, Element, ElementDetail, ElementRef, Impact, ImportResult, OntologySummary } from '@/features/ontologies/api';
import type { Comparison, ElementChange, ReleaseSummary } from '@/features/releases/api';
import { countDecisions, type ChangeItem, type ChangeSetDetail } from '@/features/review/api';

// Ids are not numbers on purpose: the router parses numeric search values as numbers.
export const ONTOLOGY_ID = 'onto-steel';
const CREATED_AT = '2026-11-20T08:00:00Z';

export function ontologyFixture(overrides: Partial<OntologySummary> = {}): OntologySummary {
  return {
    id: ONTOLOGY_ID,
    key: 'steel',
    name: '钢铁冶金',
    description: null,
    baseIri: 'https://example.org/ontology/steel#',
    ontologyIri: 'https://example.org/ontology/steel',
    entityTypeCount: 2,
    relationTypeCount: 1,
    propertyCount: 1,
    constraintCount: 0,
    axiomCount: 0,
    openChangeSetCount: 0,
    activeReleaseId: null,
    activeReleaseVersion: null,
    createdAt: CREATED_AT,
    updatedAt: CREATED_AT,
    ...overrides,
  };
}

export function documentFixture(overrides: Partial<DocumentInfo> = {}): DocumentInfo {
  return {
    id: 'doc-converter',
    ontologyId: ONTOLOGY_ID,
    filename: '转炉炼钢工艺规程.docx',
    mediaType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    sizeBytes: 128_000,
    sha256: 'a'.repeat(64),
    status: 'ready',
    progress: { step: 'changeset', done: 1, total: 1 },
    errorCode: null,
    pageCount: 12,
    charCount: 24_000,
    changeSetId: null,
    uploadedBy: '00000000-0000-4000-8000-000000000001',
    createdAt: CREATED_AT,
    updatedAt: CREATED_AT,
    ...overrides,
  };
}

export function elementFixture(overrides: Partial<Element> = {}): Element {
  return {
    id: 'el-molten-steel',
    ontologyId: ONTOLOGY_ID,
    kind: 'entity_type',
    localName: 'MoltenSteel',
    iri: 'https://example.org/ontology/steel#MoltenSteel',
    explicitIri: false,
    labelZh: '钢水',
    labelEn: 'Molten steel',
    definitionZh: '转炉冶炼得到的液态钢。',
    definitionEn: null,
    synonyms: [],
    parentId: null,
    domainId: null,
    rangeId: null,
    inverseId: null,
    datatype: null,
    unit: null,
    required: false,
    multiple: false,
    autoShape: true,
    rules: null,
    turtle: null,
    subjectId: null,
    flags: [],
    status: 'active',
    origin: 'ai',
    revision: 1,
    createdAt: CREATED_AT,
    updatedAt: CREATED_AT,
    ...overrides,
  };
}

/** An axiom: no names or IRI, only its Turtle and the element it belongs to. */
export function axiomFixture(overrides: Partial<Element> = {}): Element {
  return elementFixture({
    id: 'el-axiom-disjoint',
    kind: 'axiom',
    localName: null,
    iri: null,
    labelZh: null,
    labelEn: null,
    definitionZh: null,
    autoShape: false,
    turtle: 'steel:MoltenSteel owl:disjointWith steel:Slag .',
    subjectId: 'el-molten-steel',
    origin: 'import',
    ...overrides,
  });
}

export function importResultFixture(overrides: Partial<ImportResult> = {}): ImportResult {
  return {
    ontology: ontologyFixture(),
    changeSetId: 'cs-import',
    counts: { create: 12, update: 2, delete: 1, restore: 0 },
    warnings: [],
    ...overrides,
  };
}

export function elementDetailFixture(element: Element, provenance: ElementDetail['provenance'] = []): ElementDetail {
  return { ...element, provenance };
}

export function itemFixture(overrides: Partial<ChangeItem> = {}): ChangeItem {
  return {
    id: 'item-ladle',
    seq: 1,
    op: 'create',
    kind: 'entity_type',
    targetElementId: null,
    tempRef: 'new:Ladle',
    proposed: { localName: 'Ladle', labelZh: '钢包', labelEn: 'Ladle', definitionZh: '盛装和运送钢水的容器。', synonyms: [] },
    edited: null,
    before: null,
    decision: 'pending',
    confidence: 0.92,
    rationale: '原文多次出现并给出了定义。',
    flags: [],
    note: null,
    decidedBy: null,
    decidedAt: null,
    appliedElementId: null,
    evidence: [],
    ...overrides,
  };
}

export function changeSetFixture(items: ChangeItem[], overrides: Partial<ChangeSetDetail> = {}): ChangeSetDetail {
  return {
    id: 'cs-converter',
    ontologyId: ONTOLOGY_ID,
    title: '识别：转炉炼钢工艺规程.docx',
    source: 'ai_extraction',
    documentId: 'doc-converter',
    status: 'open',
    counts: countDecisions(items),
    createdBy: null,
    createdAt: CREATED_AT,
    mergedAt: null,
    items,
    ...overrides,
  };
}

export function releaseFixture(overrides: Partial<ReleaseSummary> = {}): ReleaseSummary {
  return {
    id: 'rel-one',
    ontologyId: ONTOLOGY_ID,
    version: 1,
    title: '首版',
    notes: null,
    elementCount: 4,
    isActive: false,
    createdBy: null,
    createdAt: CREATED_AT,
    ...overrides,
  };
}

/** What refers to an element: nothing unless the overrides say so. */
export function impactFixture(elementId: string, overrides: Partial<Impact> = {}): Impact {
  return { elementId, subtypes: [], relations: [], properties: [], constraints: [], axioms: [], inverse: null, cascade: [], ...overrides };
}

/** How an impact names an element: its Chinese, English or local name, or an axiom's Turtle. */
export function elementRefFixture(element: Element): ElementRef {
  return {
    id: element.id,
    kind: element.kind,
    label: element.labelZh ?? element.labelEn ?? element.localName ?? element.turtle ?? '',
    iri: element.iri,
  };
}

/**
 * What merging a manual save does to the elements a fake server holds: each target moves to its
 * next revision, deletes and restores also change its status. Fields are left as they were.
 */
export function mergeEdits(elements: Element[], { items }: EditRequest): void {
  for (const item of items) {
    const index = elements.findIndex((element) => element.id === item.targetElementId);
    const target = elements[index];
    if (!target) continue;
    const status = item.op === 'delete' ? 'deprecated' : item.op === 'restore' ? 'active' : target.status;
    elements[index] = { ...target, status, revision: target.revision + 1 };
  }
}

/** A request to the AI assistant; queued unless the overrides say otherwise. */
export function assistantRequestFixture(overrides: Partial<AssistantRequest> = {}): AssistantRequest {
  return {
    id: 'req-ladle',
    ontologyId: ONTOLOGY_ID,
    message: '给钢包加一个属性“容量”，单位为吨',
    context: { page: 'ontology', elementId: null },
    status: 'queued',
    step: null,
    reply: null,
    dropped: 0,
    changeSetId: null,
    errorCode: null,
    createdAt: CREATED_AT,
    finishedAt: null,
    ...overrides,
  };
}

export function elementChangeFixture(overrides: Partial<ElementChange> = {}): ElementChange {
  return {
    elementId: 'el-molten-steel',
    kind: 'entity_type',
    label: '钢水',
    iri: 'https://example.org/ontology/steel#MoltenSteel',
    change: 'changed',
    level: 'compatible',
    fields: [],
    ...overrides,
  };
}

/** A comparison from release v2 (`rel-two`) to the working version; counts follow the changes. */
export function comparisonFixture(changes: ElementChange[] = [], overrides: Partial<Comparison> = {}): Comparison {
  const count = (level: ElementChange['level']) => changes.filter((change) => change.level === level).length;
  return {
    from: { releaseId: 'rel-two', version: 2 },
    to: { releaseId: null, version: null },
    changes,
    counts: { breaking: count('breaking'), review: count('review'), compatible: count('compatible') },
    ...overrides,
  };
}
