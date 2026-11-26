import type { components } from '@/api/schema';
import { ONTOLOGY_ID, ontologyFixture } from '@/test/fixtures';
import { mockApi, userWithRole, type RouteHandler } from '@/test/utils';

export const typesPath = `/api/ontologies/${ONTOLOGY_ID}/objects/types`;
export const searchPath = `/api/ontologies/${ONTOLOGY_ID}/objects/search`;
export const release = { id: 'release-3', version: 3 };
export const heatType: components['schemas']['ObjectTypeInfo'] = {
  typeId: 'heat', label: '炉次', localName: 'Heat', iri: null,
  keyColumns: ['heat_no', 'line'], problem: null, relations: [],
  properties: [
    { propertyId: 'grade', label: '钢种', datatype: 'string', unit: null, ops: ['eq', 'in', 'isNull'] },
    { propertyId: 'weight', label: '重量', datatype: 'decimal', unit: 't', ops: ['gt', 'le'] },
    { propertyId: 'count', label: '数量', datatype: 'integer', unit: null, ops: ['eq'] },
    { propertyId: 'checked', label: '已检验', datatype: 'boolean', unit: null, ops: ['eq', 'notNull'] },
  ],
};
export const heatRow: components['schemas']['ObjectRow'] = {
  typeId: 'heat', key: 'opaque-heat', truncated: ['grade'],
  values: { grade: 'Q235', weight: '123.45000', count: '9007199254740993', checked: false },
  source: {
    dataSourceId: 'mes', dataSourceName: '钢铁 MES', schema: 'mes', table: 'heat',
    key: [{ column: 'heat_no', value: 'H2401001' }, { column: 'line', value: 'A' }],
  },
};
export const firstPage: components['schemas']['ObjectPage'] = {
  release, typeId: heatType.typeId, items: [heatRow], nextCursor: null,
};

export function mockExplore(routes: Record<string, RouteHandler> = {}, role: Parameters<typeof userWithRole>[0] = 'viewer') {
  return mockApi({
    'GET /api/ontologies': () => [ontologyFixture()],
    [`GET ${typesPath}`]: () => ({ release, items: [heatType] }),
    [`POST ${searchPath}`]: () => firstPage,
    ...routes,
  }, { user: userWithRole(role) });
}
