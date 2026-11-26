import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { elementDetailFixture, elementFixture, impactFixture, ontologyFixture } from '@/test/fixtures';
import { mockApi, renderApp, userWithRole } from '@/test/utils';

const heat = elementFixture({ id: 'el-heat', localName: 'Heat', labelZh: '炉次', labelEn: 'Heat', definitionZh: null });
const tableBinding = { id: 'bd-heat', kind: 'type_binding' as const, label: '炉次 → mes.heat', iri: null };
const columnBinding = { id: 'bd-weight', kind: 'property_binding' as const, label: '重量 → mes.heat.weight_t', iri: null };

function server() {
  return mockApi(
    {
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/ontologies/:id/elements': () => [heat],
      'GET /api/ontologies/:id/elements/:elementId': () => elementDetailFixture(heat),
      'GET /api/ontologies/:id/elements/:elementId/impact': () =>
        impactFixture('el-heat', {
          bindings: [tableBinding],
          cascade: [
            { op: 'delete', element: columnBinding },
            { op: 'delete', element: tableBinding },
          ],
        }),
      'GET /api/ontologies/:id/bindings': () => [{ typeId: 'el-heat', table: null, properties: [], relations: [], openChangeSetIds: [] }],
      'GET /api/ontologies/:id/graph': () => ({ nodes: [], edges: [] }),
    },
    { user: userWithRole('editor') },
  );
}

describe('impact of bound elements', () => {
  it('lists the bindings among what refers to a type and among what deleting it takes along', async () => {
    const user = userEvent.setup();
    server();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    await user.click(within(table).getByRole('button', { name: '炉次' }));
    const sheet = await screen.findByRole('dialog', { name: '炉次' });

    expect(await within(sheet).findByText('数据绑定（1）')).toBeInTheDocument();
    // A binding has no panel of its own to open.
    expect(within(sheet).getByText('炉次 → mes.heat')).toBeInTheDocument();
    expect(within(sheet).queryByRole('button', { name: '炉次 → mes.heat' })).not.toBeInTheDocument();

    await user.click(within(sheet).getByRole('button', { name: '删除' }));
    const dialog = await screen.findByRole('dialog', { name: /删除/ });
    const deleted = await within(dialog).findByRole('list', { name: /一并删除/ });
    expect(within(deleted).getByText('重量 → mes.heat.weight_t')).toBeInTheDocument();
    expect(within(deleted).getByText('属性绑定')).toBeInTheDocument();
    expect(within(deleted).getByText('类型绑定')).toBeInTheDocument();
  });
});
