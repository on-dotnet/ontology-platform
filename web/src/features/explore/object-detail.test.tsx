import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { components } from '@/api/schema';
import { problemResponse, renderApp } from '@/test/utils';

import { heatRow, heatType, mockExplore, release, typesPath } from './test-fixtures';

type ObjectRelation = components['schemas']['ObjectRelation'];
type ObjectRow = components['schemas']['ObjectRow'];

const heatPath = '/api/ontologies/onto-steel/objects/heat/opaque-heat';
const relatedPath = `${heatPath}/related`;
const furnacePath = '/api/ontologies/onto-steel/objects/furnace/opaque-f2';
const incoming: ObjectRelation = {
  relationId: 'fired', direction: 'in', label: '冶炼自', otherTypeId: 'furnace', otherTypeLabel: '高炉',
};
const outgoing: ObjectRelation = { ...incoming, direction: 'out', label: '供应至' };

function furnace(key: string, number: string): ObjectRow {
  return {
    typeId: 'furnace', key, values: {}, truncated: [],
    source: { ...heatRow.source, table: 'furnace', key: [{ column: 'furnace_no', value: number }] },
  };
}

async function openHeat(expireCursor = false) {
  const user = userEvent.setup();
  const first = furnace('opaque-f1', 'F-01');
  const second = furnace('opaque-f2', 'F-02');
  const api = mockExplore({
    [`GET ${typesPath}`]: () => ({
      release,
      items: [
        { ...heatType, relations: [incoming, outgoing] },
        { ...heatType, typeId: 'furnace', label: '高炉', keyColumns: ['furnace_no'], properties: [], relations: [] },
      ],
    }),
    [`GET ${heatPath}`]: () => ({
      ...heatRow, release, relations: [incoming, outgoing],
      values: { ...heatRow.values, weight: '1630.0400', unbound: 'hidden-value' },
    } satisfies components['schemas']['ObjectDetail']),
    [`GET ${relatedPath}`]: ({ query }) => {
      const previousPage = query.get('cursor');
      if (expireCursor && previousPage !== null) return problemResponse(422, 'query.invalid_cursor');
      const hasObjects = query.get('relationId') === 'fired' && query.get('direction') === 'in';
      const items = hasObjects ? (previousPage === null ? [first] : [second]) : [];
      return {
        release, typeId: 'furnace', items, nextCursor: hasObjects && previousPage === null ? 'next/f+2' : null,
      } satisfies components['schemas']['ObjectPage'];
    },
    [`GET ${furnacePath}`]: () => ({ ...second, release, relations: [] } satisfies components['schemas']['ObjectDetail']),
  });
  renderApp('/explore');
  await user.click(await screen.findByRole('button', { name: 'H2401001 · A' }));
  await screen.findByRole('region', { name: '关系' });
  return { api, user };
}

describe('object detail', () => {
  it('shows bound detail values and the ordered composite source key without exposing the opaque key', async () => {
    const { api } = await openHeat();
    expect(api.calls('GET', heatPath)).toHaveLength(1);
    const properties = within(screen.getByRole('region', { name: '属性' }));
    expect(properties.getByText(/重量/)).toBeVisible();
    expect(properties.getByText(/1630\.0400/)).toBeVisible();
    expect(document.body).not.toHaveTextContent('hidden-value');
    expect(document.body).not.toHaveTextContent('opaque-heat');
    expect(screen.getByRole('region', { name: '来源' })).toHaveTextContent(
      '来自 钢铁 MES · mes.heat · heat_no = H2401001 · line = A',
    );
  });

  it('loads each direction only when opened and shows an empty group independently', async () => {
    const { api, user } = await openHeat();
    const relations = within(screen.getByRole('region', { name: '关系' }));
    const inbound = relations.getByRole('button', { name: '冶炼自', expanded: false });
    const outbound = relations.getByRole('button', { name: '供应至', expanded: false });
    expect(api.calls('GET', relatedPath)).toHaveLength(0);

    await user.click(inbound);
    expect(await relations.findByRole('button', { name: 'F-01' })).toBeVisible();
    const calls = api.calls('GET', relatedPath);
    expect(calls).toHaveLength(1);
    expect(calls[0]?.query.get('relationId')).toBe('fired');
    expect(calls[0]?.query.get('direction')).toBe('in');
    expect(calls[0]?.query.has('cursor')).toBe(false);

    await user.click(outbound);
    expect(await relations.findByText('没有相关对象')).toBeVisible();
    expect(api.calls('GET', relatedPath)[1]?.query.get('direction')).toBe('out');
    expect(relations.getByRole('button', { name: 'F-01' })).toBeVisible();
    await user.click(inbound);
    expect(relations.queryByRole('button', { name: 'F-01' })).not.toBeInTheDocument();
    expect(relations.getByText('没有相关对象')).toBeVisible();
  });

  it('pages a relationship by cursor, opens the selected object and returns through the breadcrumb', async () => {
    const { api, user } = await openHeat();
    const relations = within(screen.getByRole('region', { name: '关系' }));
    await user.click(relations.getByRole('button', { name: '冶炼自' }));
    await user.click(await relations.findByRole('button', { name: '下一页' }));
    const target = await relations.findByRole('button', { name: 'F-02' });
    const page = api.calls('GET', relatedPath)[1];
    expect(page?.query.get('cursor')).toBe('next/f+2');
    expect(page?.query.get('relationId')).toBe('fired');
    expect(page?.query.get('direction')).toBe('in');
    expect(relations.queryByRole('button', { name: '下一页' })).not.toBeInTheDocument();
    expect(relations.queryByRole('button', { name: 'F-01' })).not.toBeInTheDocument();

    await user.click(target);
    expect(await screen.findByText('没有可浏览的关系')).toBeVisible();
    expect(screen.getByText('还没有绑定属性')).toBeVisible();
    expect(api.calls('GET', furnacePath)).toHaveLength(1);
    expect(screen.getByRole('region', { name: '来源' })).toHaveTextContent('furnace_no = F-02');
    const trail = within(screen.getByRole('navigation', { name: '浏览路径' }));
    await user.click(trail.getByRole('button', { name: 'H2401001 · A' }));
    expect(await screen.findByRole('button', { name: '冶炼自', expanded: false })).toBeVisible();
    expect(screen.getByRole('region', { name: '来源' })).toHaveTextContent('heat_no = H2401001');
  });

  it('recovers an expired relationship cursor inside the expanded group', async () => {
    const { api, user } = await openHeat(true);
    const relations = within(screen.getByRole('region', { name: '关系' }));
    await user.click(relations.getByRole('button', { name: '冶炼自' }));
    await user.click(await relations.findByRole('button', { name: '下一页' }));
    const alert = within(await relations.findByRole('alert'));
    expect(alert.getByText('当前分页位置已失效')).toBeVisible();
    await user.click(alert.getByRole('button', { name: '重新查询' }));
    expect(await relations.findByRole('button', { name: 'F-01' })).toBeVisible();
    await waitFor(() => expect(api.calls('GET', relatedPath).map((r) => r.query.get('cursor'))).toEqual([null, 'next/f+2', null]));
  });
});
