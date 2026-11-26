import { render, screen, within } from '@testing-library/react';
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
];

function setup(filters: Filter[] = []) {
  const onChange = vi.fn<(next: Filter[]) => void>();
  const view = (current: Filter[]) => <FilterEditor properties={properties} filters={current} onChange={onChange} />;
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
