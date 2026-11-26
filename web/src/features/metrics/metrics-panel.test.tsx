import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { release, typesPath } from '@/features/explore/test-fixtures';
import { ONTOLOGY_ID } from '@/test/fixtures';
import { problemResponse } from '@/test/utils';

import { evaluatePath, metric, metricsPath, openMetrics, value } from './test-fixtures';

describe('published metrics', () => {
  it('calculates only the requested metric and shows the ratio counts, scans and release below its row', async () => {
    let finish!: () => void;
    const pending = new Promise<void>((resolve) => { finish = resolve; });
    const api = openMetrics({
      [`GET ${metricsPath}`]: () => ({ release, items: [metric, { ...metric, metricId: 'other', label: '另一指标' }] }),
      [`POST ${evaluatePath}`]: async () => { await pending; return { ...value, unit: '%' }; },
    });
    const table = within(await screen.findByRole('table', { name: '指标' }));
    const row = table.getByRole('row', { name: /检验合格率/ });
    expect(row).toHaveTextContent('质量检验');
    expect(row).toHaveTextContent('占比');
    expect(api.calls('POST', evaluatePath)).toHaveLength(0);
    const calculate = within(row).getByRole('button', { name: '计算指标值' });
    fireEvent.click(calculate);
    expect(await table.findByRole('status')).toHaveTextContent('加载中');
    expect(calculate).toBeDisabled();
    finish();
    const result = await table.findByRole('row', { name: /92.3%/ });
    expect(result.textContent?.match(/%/g)).toHaveLength(1);
    expect(row.nextElementSibling).toBe(result);
    for (const field of ['符合条件的记录数36', '总体记录数39', '空值个数0', '扫描行数75', '依据版本 v3']) {
      expect(result).toHaveTextContent(field);
    }
    expect(api.calls('POST', evaluatePath).map((request) => request.body)).toEqual([{}]);
  });

  it('explains an empty population and keeps both zero counts visible', async () => {
    openMetrics({ [`POST ${evaluatePath}`]: () => ({
      ...value, value: null, display: null, reason: 'empty_population', matched: 0, population: 0, steps: [],
    }) });
    fireEvent.click(await screen.findByRole('button', { name: '计算指标值' }));
    const result = await screen.findByRole('row', { name: /没有符合条件的记录/ });
    expect(result).toHaveTextContent('符合条件的记录数0');
    expect(result).toHaveTextContent('总体记录数0');
  });

  it('preserves the decimal display and skipped null count for a non-ratio metric', async () => {
    openMetrics({
      [`GET ${metricsPath}`]: () => ({ release, items: [{ ...metric, aggregate: 'sum', label: '钢卷总重量', unit: 't' }] }),
      [`POST ${evaluatePath}`]: () => ({
        ...value, aggregate: 'sum', label: '钢卷总重量', value: '9007199254740993.01', display: '9007199254740993.01',
        unit: 't', matched: null, population: 39, nulls: 2, steps: value.steps.slice(0, 1),
      }),
    });
    fireEvent.click(await screen.findByRole('button', { name: '计算指标值' }));
    const result = await screen.findByRole('row', { name: /9007199254740993\.01/ });
    expect(result).toHaveTextContent('空值个数2');
    expect(within(result).getByText('t')).toBeVisible();
    expect(within(result).queryByText('符合条件的记录数')).toBeNull();
  });

  it('asks for narrower filters in the metric row when the scan exceeds the limit', async () => {
    openMetrics({ [`POST ${evaluatePath}`]: () => problemResponse(422, 'metric.too_many_rows') });
    fireEvent.click(await screen.findByRole('button', { name: '计算指标值' }));
    const table = within(screen.getByRole('table', { name: '指标' }));
    expect(await table.findByRole('alert')).toHaveTextContent('计算涉及的记录过多，请增加筛选条件。');
    expect(table.queryByText('92.3%')).toBeNull();
  });

  it.each([
    ['metric.invalid', '指标定义有误'],
    ['query.type_not_bound', '这个类型的绑定已变更'],
  ])('localizes %s and retries the same metric', async (code, message) => {
    let failed = true;
    openMetrics({ [`POST ${evaluatePath}`]: () => failed ? problemResponse(code === 'metric.invalid' ? 422 : 409, code) : value });
    fireEvent.click(await screen.findByRole('button', { name: '计算指标值' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(message);
    failed = false;
    fireEvent.click(within(alert).getByRole('button', { name: '重试' }));
    expect(await screen.findByText('92.3%')).toBeVisible();
  });

  it.each(['editor', 'viewer'] as const)('shows the empty list with role-appropriate navigation for %s', async (role) => {
    openMetrics({ [`GET ${metricsPath}`]: () => ({ release, items: [] }) }, role);
    expect(await screen.findByText('当前版本还没有指标。')).toBeVisible();
    const link = screen.queryByRole('link', { name: '新建指标' });
    if (role === 'editor') {
      const destination = new URL(link?.getAttribute('href') ?? '/', window.location.origin);
      expect(destination.pathname).toBe('/ontology');
      expect(destination.searchParams.get('ontology')).toBe(ONTOLOGY_ID);
    } else {
      expect(link).toBeNull();
    }
  });

  it.each([metricsPath, typesPath])('replaces both cards with the publication link for no release from %s', async (path) => {
    openMetrics({ [`GET ${path}`]: () => problemResponse(409, 'query.no_release') });
    expect(await screen.findByRole('heading', { name: '本体还没有发布版本' })).toBeVisible();
    expect(screen.getByRole('link', { name: '去发布' })).toHaveAttribute('href', `/releases?ontology=${ONTOLOGY_ID}`);
    expect(screen.queryByRole('heading', { name: '指标' })).toBeNull();
    expect(screen.queryByRole('heading', { name: '规则检查' })).toBeNull();
  });

  it('retries a failed metrics list', async () => {
    let failed = true;
    openMetrics({ [`GET ${metricsPath}`]: () => failed ? problemResponse(503, 'query.busy') : { release, items: [metric] } });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('数据源正忙');
    failed = false;
    fireEvent.click(within(alert).getByRole('button', { name: '重试' }));
    expect(await screen.findByRole('row', { name: /检验合格率/ })).toBeVisible();
  });
});
