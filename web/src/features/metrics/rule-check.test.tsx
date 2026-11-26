import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { components } from '@/api/schema';
import { heatRow, heatType, release, typesPath } from '@/features/explore/test-fixtures';
import i18n from '@/i18n';

import { inspection, openMetrics, rulesPath } from './test-fixtures';

type Rule = components['schemas']['RuleResult'];
const strength: Rule = {
  constraintId: 'strength', constraintLabel: '屈服强度约束', propertyId: 'reh', propertyLabel: '屈服强度',
  message: '屈服强度至少为 235 MPa。', checks: ['minInclusive'], unchecked: [], violations: 0, samples: [],
};
function sample(index: number): components['schemas']['RuleSample'] {
  return {
    object: {
      ...heatRow, typeId: inspection.typeId, key: `opaque-${index}`,
      source: { ...heatRow.source, key: [{ column: 'inspection_no', value: `I-${index}` }] },
    },
    failed: [{ check: 'minInclusive', expected: '235', actual: '234.00' }],
  };
}
function report(results: Rule[]): components['schemas']['RuleReport'] {
  return {
    typeId: inspection.typeId, release, scanned: 43, checkedRules: results.filter((rule) => rule.checks.length).length,
    uncheckedRules: results.filter((rule) => rule.unchecked.length).length, results, steps: [],
  };
}
async function checkInspections() {
  const select = await screen.findByRole('combobox', { name: '选择对象类型' });
  fireEvent.change(select, { target: { value: inspection.typeId } });
  fireEvent.click(screen.getByRole('button', { name: '检查规则' }));
  return select;
}

describe('released rule checks', () => {
  it('checks the selected type and distinguishes passing, violated and unchecked constraints', async () => {
    const api = openMetrics({ [`POST ${rulesPath}`]: () => report([
      { ...strength, violations: 3, samples: [sample(1), sample(2), sample(3)] },
      { ...strength, constraintId: 'tensile', message: '抗拉强度在范围内。' },
      { ...strength, constraintId: 'type', constraintLabel: '数据类型约束', message: null,
        checks: [], unchecked: [{ check: 'datatype', reason: 'check_not_supported' }] },
    ]) });
    const select = await checkInspections();
    const tensile = await screen.findByRole('row', { name: /抗拉强度在范围内/ });
    expect(screen.getByText('已检查 2 条，未检查 1 条')).toBeVisible();
    expect(api.calls('POST', rulesPath)).toHaveLength(1);
    expect(api.calls('POST', rulesPath)[0]?.body).toMatchObject({ typeId: inspection.typeId });
    expect(tensile).toHaveTextContent('通过');
    const unchecked = screen.getByRole('row', { name: /数据类型约束/ });
    expect(unchecked).toHaveTextContent('未检查');
    expect(unchecked).toHaveTextContent('暂时无法检查这项要求。');
    expect(unchecked).not.toHaveTextContent('通过');
    const expand = within(screen.getByRole('row', { name: /屈服强度至少/ })).getByRole('button', { name: /违反 3 条/ });
    expect(expand).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('table', { name: '违反约束的对象' })).toBeNull();
    fireEvent.click(expand);
    const objects = within(screen.getByRole('table', { name: '违反约束的对象' }));
    expect(objects.getAllByRole('row')).toHaveLength(4);
    const row = within(objects.getByRole('row', { name: /I-1/ }));
    for (const name of ['I-1', '质量检验 · I-1', '≥ 235', '234.00']) expect(row.getByRole('cell', { name })).toBeVisible();
    expect(screen.queryByText('opaque-1')).toBeNull();
    fireEvent.click(expand);
    expect(screen.queryByRole('table', { name: '违反约束的对象' })).toBeNull();
    fireEvent.change(select, { target: { value: heatType.typeId } });
    expect(screen.queryByText('抗拉强度在范围内。')).toBeNull();
  });

  it('shows unchecked reasons alongside violations and explains the sample limit', async () => {
    openMetrics({ [`POST ${rulesPath}`]: () => report([{
      ...strength, violations: 51, samples: Array.from({ length: 50 }, (_, index) => sample(index + 1)),
      unchecked: [{ check: 'minInclusive', reason: 'value_mismatch' }],
    }]) });
    await checkInspections();
    const row = await screen.findByRole('row', { name: /屈服强度至少/ });
    expect(screen.getByText('已检查 1 条，未检查 1 条')).toBeVisible();
    expect(row).toHaveTextContent('数据值与约束要求的类型不一致。');
    fireEvent.click(within(row).getByRole('button', { name: /违反 51 条/ }));
    expect(screen.getByText('仅显示 51 个违反对象中的 50 个。')).toBeVisible();
    expect(within(screen.getByRole('table', { name: '违反约束的对象' })).getAllByRole('row')).toHaveLength(51);
  });

  it('keeps separate property rules of the same constraint identifiable when their order changes', async () => {
    const first = { ...strength, message: '满足强度下限。', violations: 1, samples: [sample(1)] };
    const second = { ...first, propertyId: 'rm', propertyLabel: '抗拉强度', samples: [sample(2)] };
    let reversed = false;
    openMetrics({ [`POST ${rulesPath}`]: () => report(reversed ? [second, first] : [first, second]) });
    await checkInspections();
    const table = within(await screen.findByRole('table', { name: '规则检查' }));
    const toggle = (property: string) => within(table.getByRole('row', { name: new RegExp(property) })).getByRole('button');
    fireEvent.click(toggle('屈服强度'));
    expect(toggle('抗拉强度')).toHaveAttribute('aria-expanded', 'false');
    reversed = true;
    fireEvent.click(screen.getByRole('button', { name: '检查规则' }));
    await waitFor(() => expect(table.getAllByRole('row')[1]).toHaveTextContent('抗拉强度'));
    expect(toggle('屈服强度')).toHaveAttribute('aria-expanded', 'true');
    expect(toggle('抗拉强度')).toHaveAttribute('aria-expanded', 'false');
    expect(within(screen.getByRole('table', { name: '违反约束的对象' })).getByText('I-1')).toBeVisible();
  });

  it('keeps each failed requirement paired with its own actual value', async () => {
    const object = sample(1);
    openMetrics({ [`POST ${rulesPath}`]: () => report([{
      ...strength, checks: ['minInclusive', 'allowedValues'], violations: 1, samples: [{
        ...object, failed: [...object.failed, { check: 'allowedValues', expected: [235, 275], actual: '234.00' }],
      }],
    }]) });
    await checkInspections();
    fireEvent.click(await screen.findByRole('button', { name: /违反 1 条/ }));
    const table = within(screen.getByRole('table', { name: '违反约束的对象' }));
    expect(table.getAllByRole('row')).toHaveLength(3);
    expect(table.getByRole('row', { name: /≥ 235/ })).toHaveTextContent('234.00');
    expect(table.getByRole('row', { name: /取值须为 235，275 之一/ })).toHaveTextContent('234.00');
  });

  it('shows the empty state only after a check finds no constraints', async () => {
    openMetrics({ [`POST ${rulesPath}`]: () => report([]) });
    await screen.findByRole('button', { name: '检查规则' });
    expect(screen.queryByText('这个对象类型还没有约束。')).toBeNull();
    await checkInspections();
    expect(await screen.findByText('这个对象类型还没有约束。')).toBeVisible();
    expect(screen.getByText('已检查 0 条，未检查 0 条')).toBeVisible();
  });

  it('keeps the metric list available when there are no bound types to check', async () => {
    openMetrics({ [`GET ${typesPath}`]: () => ({ release, items: [] }) });
    expect(await screen.findByText('还没有绑定数据')).toBeVisible();
    expect(screen.getByRole('table', { name: '指标' })).toBeVisible();
    expect(screen.queryByRole('button', { name: '检查规则' })).toBeNull();
  });

  it('requests rule messages in the selected language and refreshes an open report on language change', async () => {
    const languages: (string | null)[] = [];
    openMetrics({ [`POST ${rulesPath}`]: ({ request }) => {
      const language = request.headers.get('Accept-Language');
      languages.push(language);
      return report([{ ...strength, message: language === 'en' ? 'Yield strength must be at least 235 MPa.' : strength.message }]);
    } });
    await checkInspections();
    expect(await screen.findByText('屈服强度至少为 235 MPa。')).toBeVisible();
    await act(async () => { await i18n.changeLanguage('en'); });
    expect(await screen.findByText('Yield strength must be at least 235 MPa.')).toBeVisible();
    expect(screen.queryByText('屈服强度至少为 235 MPa。')).toBeNull();
    expect(languages).toEqual(['zh-CN', 'en']);
  });
});
