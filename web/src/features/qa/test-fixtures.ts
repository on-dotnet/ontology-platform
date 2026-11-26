import type { components } from '@/api/schema';
import { ONTOLOGY_ID, ontologyFixture } from '@/test/fixtures';
import { mockApi, userWithRole, type RouteHandler } from '@/test/utils';

type Question = components['schemas']['QaQuestion'];

export const listPath = `/api/ontologies/${ONTOLOGY_ID}/qa/questions`;
export const detailPath = '/api/qa/questions/q1';
export const queued: Question = {
  id: 'q1', ontologyId: ONTOLOGY_ID, question: '哪些钢卷需要复检？', origin: 'user', cqQuestionId: null,
  askedBy: userWithRole('viewer'), status: 'queued', step: null, release: null, plan: null,
  gaps: null, answer: null, evidence: null, gapProposal: null, errorCode: null,
  createdAt: '2026-11-25T12:00:00Z', finishedAt: null,
};

function row(typeId: string, key: string, number: string): components['schemas']['PathRow'] {
  return {
    typeId, key, values: {}, truncated: [], via: [],
    source: { dataSourceId: 'mes', dataSourceName: 'MES', schema: 'mes', table: typeId, key: [{ column: 'number', value: number }] },
  };
}

export const evidence: components['schemas']['QaEvidence'] = {
  release: { id: 'v3', version: 3 },
  elements: [
    { id: 'coil', label: '钢卷', iri: null, kind: 'entity_type', documents: [
      { documentId: 'doc', documentName: '质量规程', chunk: 4, quote: '复检须由质量组确认。' },
    ] },
    { id: 'grade', label: '钢种', iri: null, kind: 'property', documents: [] },
  ],
  bindings: [{ schema: 'mes', table: 'coil', keyColumns: ['number'] }],
  steps: [{ typeId: 'coil', typeLabel: '钢卷', conditions: ['是否合格 = 否'], statements: 1, rows: 2, truncated: false }],
  rows: [{ ...row('coil', 'encoded-coil', 'W2401'), values: { grade: 'Q235B' } }],
  tail: [row('inspection', 'encoded-test', 'TEST-07')], truncated: false, metric: null, rules: null,
};

export const answer: components['schemas']['QaAnswer'] = {
  text: '复检对象来自不合格的检验记录。', facts: {
    count: 2, metric: { label: '合格率', display: '97.5%' },
    objects: [{ typeId: 'coil', key: 'encoded-coil', label: '一号钢卷' }], violations: 0,
  }, citedKeys: ['encoded-coil'], counterpoints: ['同一卷可能有多条记录。'], notes: [],
};

export const answered: Question = {
  ...queued, status: 'answered', step: 'done', answer, evidence, release: evidence.release,
  plan: { intent: 'objects', start: null, hops: [], target: 0, metricId: null, description: '',
    assumptions: ['仅统计已完成的检验。'] },
};

export function qaServer(items: Question[] = [], routes: Record<string, RouteHandler> = {}) {
  return mockApi({
    'GET /api/ontologies': () => [ontologyFixture()],
    [`GET ${listPath}`]: (): components['schemas']['QaQuestionList'] => ({
      items: items.map((q) => ({ ...q, evidence: null })), nextCursor: null,
    }),
    'GET /api/qa/questions/:id': ({ params }) => items.find((q) => q.id === params.id),
    [`POST ${listPath}`]: () => { items.unshift(queued); return queued; },
    ...routes,
  }, { user: userWithRole('viewer') });
}
