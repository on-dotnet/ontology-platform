import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { components } from '@/api/schema';
import { heatRow, heatType, release, typesPath } from '@/features/explore/test-fixtures';
import i18n from '@/i18n';
import { problemResponse } from '@/test/utils';

import { evaluatePath, inspection, metric, metricsPath, openMetrics, rulesPath, value } from './test-fixtures';

const nextRelease = { id: 'release-4', version: 4 };
const result: components['schemas']['RuleResult'] = {
  constraintId: 'reh', constraintLabel: '屈服强度约束', message: '屈服强度至少为 235 MPa。',
  propertyId: 'strength', propertyLabel: '屈服强度', checks: ['minInclusive'], unchecked: [], violations: 1,
  samples: [{ object: { ...heatRow, typeId: inspection.typeId }, failed: [{ check: 'minInclusive', expected: 235, actual: 230 }] }],
};
const report: components['schemas']['RuleReport'] = {
  release, typeId: inspection.typeId, scanned: 1, checkedRules: 1, uncheckedRules: 0, results: [result], steps: [],
};

describe('recovering metric and rule results', () => {
  it('refreshes the catalog and removes a missing metric without evaluating the obsolete row again', async () => {
    let removed = false;
    const api = openMetrics({
      [`GET ${metricsPath}`]: () => ({ release, items: removed ? [] : [metric] }),
      [`POST ${evaluatePath}`]: () => { removed = true; return problemResponse(404, 'metric.not_found'); },
    });
    fireEvent.click(await screen.findByRole('button', { name: '计算指标值' }));
    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent('当前版本没有这个指标');
    fireEvent.click(within(error).getByRole('button', { name: '重试' }));
    expect(await screen.findByText('当前版本还没有指标。')).toBeVisible();
    expect(screen.queryByText(metric.label)).toBeNull();
    expect(api.calls('GET', metricsPath)).toHaveLength(2);
    expect(api.calls('POST', evaluatePath)).toHaveLength(1);
  });

  it.each([nextRelease, release])('recalculates the expanded metric after checking the catalog at $id', async (active) => {
    let changed = false;
    const api = openMetrics({
      [`GET ${metricsPath}`]: () => ({ release: changed ? active : release, items: [metric] }),
      [`GET ${typesPath}`]: () => ({ release: changed ? active : release, items: [inspection] }),
      [`POST ${evaluatePath}`]: () => {
        if (changed) return { ...value, release: active };
        changed = true;
        return problemResponse(409, 'query.release_changed');
      },
    });
    fireEvent.click(await screen.findByRole('button', { name: '计算指标值' }));
    await screen.findByText('本体刚发布了新版本');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    const row = await screen.findByRole('row', { name: /92.3%/ });
    expect(row).toHaveTextContent(`依据版本 v${active.version}`);
    expect(api.calls('GET', metricsPath)).toHaveLength(2);
    expect(api.calls('POST', evaluatePath)).toHaveLength(2);
  });

  it('rechecks the selected type and restores expanded violations from the new release', async () => {
    let active = release;
    const api = openMetrics({
      [`GET ${metricsPath}`]: () => ({ release: active, items: [] }),
      [`GET ${typesPath}`]: () => ({ release: active, items: [heatType, inspection] }),
      [`POST ${rulesPath}`]: () => ({ ...report, release: active, results: [{
        ...result, message: `屈服强度 v${active.version}`,
      }] }),
    });
    const selector = await screen.findByRole('combobox', { name: '选择对象类型' });
    fireEvent.change(selector, { target: { value: inspection.typeId } });
    const check = screen.getByRole('button', { name: '检查规则' });
    fireEvent.click(check);
    fireEvent.click(await screen.findByRole('button', { name: '违反 1 条' }));
    active = nextRelease;
    fireEvent.click(check);
    await screen.findByText('本体刚发布了新版本');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByText('屈服强度 v4')).toBeVisible();
    expect(screen.getByRole('combobox', { name: '选择对象类型' })).toHaveValue(inspection.typeId);
    expect(screen.getByRole('button', { name: '违反 1 条' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('table', { name: '违反约束的对象' })).toBeVisible();
    expect(api.calls('GET', typesPath)).toHaveLength(2);
    expect(api.calls('POST', rulesPath).map((call) => call.body)).toEqual(
      Array.from({ length: 3 }, () => ({ typeId: inspection.typeId, limit: 50 })),
    );
  });

  it.each([
    ['zh-CN', '检查规则', '当前对象类型的记录过多', '重试', '这个对象类型还没有约束。'],
    ['en', 'Check rules', 'Too many records for the selected object type', 'Retry', 'This object type has no constraints yet.'],
  ])('explains an oversized rule check in %s and retries the selected type', async (language, check, message, retry, empty) => {
    await i18n.changeLanguage(language);
    let failed = true;
    const api = openMetrics({ [`POST ${rulesPath}`]: () => failed ? problemResponse(422, 'query.too_many_rows') : {
      ...report, typeId: heatType.typeId, checkedRules: 0, results: [],
    } });
    fireEvent.click(await screen.findByRole('button', { name: check }));
    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent(message);
    failed = false;
    fireEvent.click(within(error).getByRole('button', { name: retry }));
    expect(await screen.findByText(empty)).toBeVisible();
    expect(api.calls('POST', rulesPath)).toHaveLength(2);
    expect(api.calls('GET', metricsPath)).toHaveLength(1);
  });
});
