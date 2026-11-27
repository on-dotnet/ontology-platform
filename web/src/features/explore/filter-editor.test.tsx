import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { components } from '@/api/schema';

import { FilterEditor } from './filter-editor';

type Filter = components['schemas']['Filter'];
const properties: components['schemas']['ObjectProperty'][] = [
  { propertyId: 'code', label: '炉号', datatype: 'string', unit: null, ops: ['eq', 'in'] },
  { propertyId: 'weight', label: '重量', datatype: 'decimal', unit: 'kg', ops: ['gt', 'in'] },
  { propertyId: 'count', label: '数量', datatype: 'integer', unit: null, ops: ['eq', 'in'] },
  { propertyId: 'active', label: '生效', datatype: 'boolean', unit: null, ops: ['ne', 'isNull', 'notNull'] },
  { propertyId: 'day', label: '日期', datatype: 'date', unit: null, ops: ['eq', 'in'] },
  { propertyId: 'time', label: '时间', datatype: 'dateTime', unit: null, ops: ['eq', 'in'] },
];

const timeHint = '如 08:30、08:30:00 或 08:30:00+08:00';
const optionalHint = '只记录日期的数据请留空时间，其他数据必须填写，如 08:30、08:30:00 或 08:30:00+08:00';
const invalidTime = '请输入有效时间，如 08:30、08:30:00 或 08:30:00+08:00';

function setup(filters: Filter[] = [], optionalTime = false) {
  const onChange = vi.fn<(next: Filter[]) => void>();
  const view = (current: Filter[]) => (
    <FilterEditor properties={properties} filters={current} onChange={onChange} optionalTime={optionalTime} />
  );
  const { rerender } = render(view(filters));
  const user = userEvent.setup({ delay: null });
  return {
    onChange, user, update: (next: Filter[]) => rerender(view(next)),
    open: () => user.click(screen.getByRole('button', { name: '添加筛选' })),
    property: () => screen.getByRole('combobox', { name: '选择属性' }),
    operator: () => screen.getByRole('combobox', { name: '选择运算符' }),
    apply: () => user.click(screen.getByRole('button', { name: '应用筛选' })),
  };
}

describe('FilterEditor', () => {
  it('picks a date for a date property without asking for a time', async () => {
    const { user, open, property, apply, onChange } = setup();
    await open();
    await user.selectOptions(property(), 'day');
    const date = screen.getByLabelText(/^筛选值/);
    expect(date).toHaveAttribute('type', 'date');
    expect(screen.queryByLabelText(/^时间/)).not.toBeInTheDocument();
    await apply();
    expect(date).toHaveAccessibleDescription('请输入筛选值');
    expect(date).toHaveFocus();
    await user.type(date, '2024-02-29');
    await apply();
    expect(onChange).toHaveBeenCalledExactlyOnceWith([{ propertyId: 'day', op: 'eq', value: '2024-02-29' }]);
  });

  it('keeps the time format visible while a time with an offset is typed', async () => {
    const { user, open, property, apply, onChange } = setup();
    await open();
    await user.selectOptions(property(), 'time');
    const date = screen.getByLabelText(/^筛选值/);
    expect(date).toHaveAttribute('type', 'date');
    const time = screen.getByLabelText(/^时间/);
    expect(time).toHaveAccessibleDescription(timeHint);
    await user.type(date, '2024-02-29');
    await user.type(time, '08:30:00.123456+08:00');
    expect(screen.getByText(timeHint)).toBeVisible();
    await apply();
    expect(onChange).toHaveBeenCalledExactlyOnceWith([
      { propertyId: 'time', op: 'eq', value: '2024-02-29T08:30:00.123456+08:00' },
    ]);
  });

  it.each(['', '25:00', '8:30', '08:30+8'])('rejects the time "%s" where one is required', async (typed) => {
    const { user, open, property, apply, onChange } = setup();
    await open();
    await user.selectOptions(property(), 'time');
    await user.type(screen.getByLabelText(/^筛选值/), '2024-02-29');
    const time = screen.getByLabelText(/^时间/);
    if (typed) await user.type(time, typed);
    await apply();
    expect(time).toHaveAccessibleDescription(`${timeHint} ${invalidTime}`);
    expect(time).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText(/^筛选值/)).toHaveAttribute('aria-invalid', 'false');
    expect(screen.getByLabelText(/^筛选值/)).not.toHaveAccessibleDescription();
    expect(time).toHaveFocus();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('sends only the date when the time is optional and left empty', async () => {
    const { user, open, property, apply, onChange } = setup([], true);
    await open();
    await user.selectOptions(property(), 'time');
    expect(screen.getByLabelText(/^时间/)).not.toBeRequired();
    // A column holding times refuses a date alone, so the hint must say when it may stay empty.
    expect(screen.getByLabelText(/^时间/)).toHaveAccessibleDescription(optionalHint);
    await user.type(screen.getByLabelText(/^筛选值/), '2024-02-29');
    await apply();
    expect(onChange).toHaveBeenCalledExactlyOnceWith([{ propertyId: 'time', op: 'eq', value: '2024-02-29' }]);
  });

  it('reports a time without a date, but only after focus leaves both fields', async () => {
    const { user, open, property, apply, onChange } = setup([], true);
    await open();
    await user.selectOptions(property(), 'time');
    await user.click(screen.getByLabelText(/^筛选值/));
    await user.click(screen.getByLabelText(/^时间/));
    await user.keyboard('08:30');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await user.click(screen.getByRole('combobox', { name: '选择属性' }));
    expect(screen.getByRole('alert')).toHaveTextContent('请输入有效日期');
    await apply();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('collects several dates with their own pickers and drops a removed one', async () => {
    const { user, open, property, operator, apply, onChange } = setup();
    await open();
    await user.selectOptions(property(), 'day');
    await user.selectOptions(operator(), 'in');
    expect(screen.getByRole('group', { name: '筛选值' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '删除第 1 个值' })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('第 1 个日期'), '2024-02-27');
    for (const [position, day] of [[2, '2024-02-28'], [3, '2024-02-29']] as const) {
      await user.click(screen.getByRole('button', { name: '添加值' }));
      expect(screen.getByLabelText(`第 ${position} 个日期`)).toHaveFocus();
      await user.type(screen.getByLabelText(`第 ${position} 个日期`), day);
    }
    await user.click(screen.getByRole('button', { name: '删除第 2 个值' }));
    // A picker reports a half-typed date as empty, so an empty row must not be dropped silently.
    await user.click(screen.getByRole('button', { name: '添加值' }));
    await apply();
    expect(screen.getByRole('alert')).toHaveTextContent('请输入有效日期');
    expect(screen.getByLabelText('第 3 个日期')).toHaveAttribute('aria-invalid', 'true');
    expect(onChange).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '删除第 3 个值' }));
    await apply();
    expect(onChange).toHaveBeenCalledExactlyOnceWith([
      { propertyId: 'day', op: 'in', value: ['2024-02-27', '2024-02-29'] },
    ]);
  });

  it('marks the incomplete member of a date and time list', async () => {
    const { user, open, property, operator, apply, onChange } = setup([], true);
    await open();
    await user.selectOptions(property(), 'time');
    await user.selectOptions(operator(), 'in');
    const group = screen.getByRole('group', { name: '筛选值' });
    expect(within(group).getByText('日期')).toBeVisible();
    expect(within(group).getByText('时间')).toBeVisible();
    await user.type(screen.getByLabelText('第 1 个日期'), '2024-02-28');
    await user.click(screen.getByRole('button', { name: '添加值' }));
    await user.type(screen.getByLabelText('第 2 个时间'), '08:30');
    expect(screen.getByLabelText('第 2 个日期')).toBeRequired();
    expect(screen.getByLabelText('第 2 个时间')).not.toBeRequired();
    await apply();
    expect(screen.getByRole('alert')).toHaveTextContent('请输入有效日期');
    expect(screen.getByLabelText('第 2 个日期')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('第 2 个日期')).toHaveAccessibleDescription('请输入有效日期');
    expect(screen.getByLabelText('第 1 个日期')).toHaveAttribute('aria-invalid', 'false');
    expect(screen.getByLabelText('第 1 个日期')).not.toHaveAccessibleDescription();
    expect(screen.getByLabelText('第 2 个时间')).toHaveAccessibleDescription(optionalHint);
    expect(onChange).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('第 2 个日期'), '2024-02-29');
    await apply();
    expect(onChange).toHaveBeenCalledExactlyOnceWith([
      { propertyId: 'time', op: 'in', value: ['2024-02-28', '2024-02-29T08:30'] },
    ]);
  });

  it('keeps focus on a neighbouring date after removing a value', async () => {
    const { user, open, property, operator } = setup();
    await open();
    await user.selectOptions(property(), 'day');
    await user.selectOptions(operator(), 'in');
    for (let count = 1; count < 3; count += 1) await user.click(screen.getByRole('button', { name: '添加值' }));
    // The middle row, then the last row, then down to a single row.
    for (const [removed, focused] of [[2, 2], [2, 1]] as const) {
      await user.click(screen.getByRole('button', { name: `删除第 ${removed} 个值` }));
      expect(screen.getByLabelText(`第 ${focused} 个日期`)).toHaveFocus();
    }
    await user.click(screen.getByRole('button', { name: '添加值' }));
    await user.click(screen.getByRole('button', { name: '删除第 1 个值' }));
    expect(screen.getByLabelText('第 1 个日期')).toHaveFocus();
  });

  it('stops adding dates at 100 values', async () => {
    const { user, open, property, operator } = setup();
    await open();
    await user.selectOptions(property(), 'day');
    await user.selectOptions(operator(), 'in');
    const add = screen.getByRole('button', { name: '添加值' });
    for (let count = 1; count < 100; count += 1) fireEvent.click(add);
    expect(screen.getByLabelText('第 100 个日期')).toBeInTheDocument();
    expect(add).toBeDisabled();
  });

  it('offers only the selected property operators and discards an abandoned draft', async () => {
    const { user, open, property, operator, onChange } = setup();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    await open();
    expect(within(operator()).getAllByRole('option').map((option) => option.textContent)).toEqual(['等于', '属于']);
    await user.type(screen.getByRole('textbox', { name: '筛选值' }), 'H2401');
    await user.selectOptions(property(), 'active');
    expect(within(operator()).getAllByRole('option').map((option) => option.textContent)).toEqual(['不等于', '为空', '不为空']);
    expect(operator()).toHaveValue('ne');
    await user.click(screen.getByRole('button', { name: '取消' }));
    await open();
    expect(screen.getByRole('textbox', { name: '筛选值' })).toHaveValue('');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('appends a multiline membership filter and removes just its chip', async () => {
    const existing: Filter = { propertyId: 'active', op: 'ne', value: false };
    const added: Filter = { propertyId: 'code', op: 'in', value: ['A,B', ' H2401 '] };
    const { user, open, operator, apply, onChange, update } = setup([existing]);
    await open();
    await user.selectOptions(operator(), 'in');
    await user.type(screen.getByRole('textbox', { name: '筛选值（每行一个）' }), 'A,B{Enter}{Enter} H2401 ');
    await apply();
    expect(onChange).toHaveBeenCalledExactlyOnceWith([existing, added]);
    update([existing, added]);
    const remove = screen.getByRole('button', { name: /移除筛选：炉号 属于.*A,B.*H2401/ });
    expect(remove).toHaveTextContent('A,B');
    expect(screen.getByRole('button', { name: '移除筛选：生效 不等于 否' })).toBeInTheDocument();
    await user.click(remove);
    expect(onChange).toHaveBeenLastCalledWith([existing]);
  });

  it.each([
    ['weight', 'gt', '0.123456789012345678900', '0.123456789012345678900'],
    ['count', 'eq', '9007199254740993', '9007199254740993'],
    ['count', 'eq', '-42', -42],
  ] as const)('submits %s %s %s without rounding', async (id, op, raw, expected) => {
    const { user, open, property, apply, onChange } = setup();
    await open();
    await user.selectOptions(property(), id);
    await user.type(screen.getByRole('textbox', { name: '筛选值' }), raw);
    await apply();
    expect(onChange).toHaveBeenCalledWith([{ propertyId: id, op, value: expected }]);
  });

  it.each([true, false])('submits a JSON boolean for %s', async (value) => {
    const { user, open, property, apply, onChange } = setup();
    await open();
    await user.selectOptions(property(), 'active');
    const select = screen.getByRole('combobox', { name: '筛选值' });
    await user.selectOptions(select, within(select).getByRole('option', { name: value ? '是' : '否' }));
    await apply();
    expect(onChange).toHaveBeenCalledWith([{ propertyId: 'active', op: 'ne', value }]);
  });

  it.each(['isNull', 'notNull'])('omits value when switching to %s', async (op) => {
    const { user, open, property, operator, apply, onChange } = setup();
    await open();
    await user.selectOptions(property(), 'active');
    await user.selectOptions(screen.getByRole('combobox', { name: '筛选值' }), 'false');
    await user.selectOptions(operator(), op);
    expect(screen.queryByRole('combobox', { name: '筛选值' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    await apply();
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0]?.[0]).toStrictEqual([{ propertyId: 'active', op }]);
  });

  it('checks every list member and accepts the corrected integer list with exact precision', async () => {
    const { user, open, property, operator, apply, onChange } = setup();
    await open();
    await user.selectOptions(property(), 'count');
    await user.selectOptions(operator(), 'in');
    const input = screen.getByRole('textbox', { name: '筛选值（每行一个）' });
    await user.type(input, '42{Enter}3.5');
    await apply();
    expect(input).toHaveAccessibleDescription('请输入整数');
    expect(onChange).not.toHaveBeenCalled();
    await user.clear(input);
    await user.type(input, '42{Enter}9007199254740993');
    await apply();
    expect(onChange).toHaveBeenCalledWith([{ propertyId: 'count', op: 'in', value: [42, '9007199254740993'] }]);
  });

  it('requires a value and accepts up to 100 membership values', async () => {
    const { user, open, operator, apply, onChange } = setup();
    await open();
    await user.selectOptions(operator(), 'in');
    const input = screen.getByRole('textbox', { name: '筛选值（每行一个）' });
    await apply();
    expect(input).toHaveAccessibleDescription('请输入筛选值');
    const values = Array.from({ length: 100 }, (_, index) => String(index));
    await user.click(input);
    await user.paste([...values, 'extra'].join('\n'));
    await apply();
    expect(input).toHaveAccessibleDescription('最多可输入 100 个值，请减少后重试');
    expect(onChange).not.toHaveBeenCalled();
    await user.clear(input);
    await user.paste(values.join('\n'));
    await apply();
    expect(onChange).toHaveBeenCalledWith([{ propertyId: 'code', op: 'in', value: values }]);
  });

  it('allows a tenth condition and requires removing one before adding another', async () => {
    const nine: Filter[] = Array.from({ length: 9 }, (_, index) => ({ propertyId: 'code', op: 'eq', value: String(index) }));
    const tenth: Filter = { propertyId: 'code', op: 'eq', value: 'last' };
    const { user, open, apply, onChange, update } = setup(nine);
    await open();
    await user.type(screen.getByRole('textbox', { name: '筛选值' }), 'last');
    await apply();
    expect(onChange).toHaveBeenCalledWith([...nine, tenth]);
    update([...nine, tenth]);
    expect(screen.getByRole('button', { name: '添加筛选' })).toBeDisabled();
    expect(screen.getByText('最多可添加 10 条筛选条件')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '移除筛选：炉号 等于 last' }));
    expect(onChange).toHaveBeenLastCalledWith(nine);
    update(nine);
    await open();
    expect(screen.getByRole('button', { name: '应用筛选' })).toBeEnabled();
  });
});
