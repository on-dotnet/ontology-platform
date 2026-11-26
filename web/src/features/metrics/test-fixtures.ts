import type { components } from '@/api/schema';
import { heatType, mockExplore, release, typesPath } from '@/features/explore/test-fixtures';
import { ONTOLOGY_ID } from '@/test/fixtures';
import { renderApp, type RouteHandler } from '@/test/utils';

export const metricsPath = `/api/ontologies/${ONTOLOGY_ID}/metrics`;
export const evaluatePath = `${metricsPath}/pass-rate/evaluate`;
export const rulesPath = `/api/ontologies/${ONTOLOGY_ID}/rules/check`;
export const inspection = { ...heatType, typeId: 'inspection', label: '质量检验' };
export const metric: components['schemas']['MetricInfo'] = {
  metricId: 'pass-rate', label: '检验合格率', aggregate: 'ratio', subjectTypeId: inspection.typeId,
  subjectTypeLabel: inspection.label, definition: null, unit: null, bound: true,
};
const step = { typeId: inspection.typeId, typeLabel: inspection.label, conditions: [], statements: 1, truncated: false };
export const value: components['schemas']['MetricValue'] = {
  release, metricId: metric.metricId, label: metric.label, aggregate: 'ratio', unit: null,
  value: '0.923076923', display: '92.3%', population: 39, matched: 36, nulls: 0,
  reason: null, steps: [{ ...step, rows: 39 }, { ...step, rows: 36 }],
};

export function openMetrics(routes: Record<string, RouteHandler> = {}, role: 'editor' | 'viewer' = 'viewer') {
  const api = mockExplore({
    [`GET ${metricsPath}`]: () => ({ release, items: [metric] }),
    [`GET ${typesPath}`]: () => ({ release, items: [heatType, inspection] }),
    ...routes,
  }, role);
  renderApp('/explore?tab=metrics');
  return api;
}
