import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';

import type { components } from '@/api/schema';
import i18n from '@/i18n';
import { elementFixture, ONTOLOGY_ID } from '@/test/fixtures';
import { jsonResponse, mockApi, problemResponse, renderWithProviders, type RouteHandler } from '@/test/utils';

import { QuestionsPanel } from './questions-panel';

type Question = components['schemas']['CompetencyQuestion'];
type Check = components['schemas']['CqCheck'];
const collection = `/api/ontologies/${ONTOLOGY_ID}/competency-questions`;
const resource = '/api/competency-questions/cq-1';
const createdAt = '2026-11-25T09:00:00Z';
const release = { id: 'steel-v2', version: 2 };
const type = elementFixture({ id: 'coil', labelZh: '钢卷' });

function question(position = 1, overrides: Partial<Question> = {}): Question {
  return {
    id: `cq-${position}`, text: `第 ${position} 条验收问题`, ontologyId: ONTOLOGY_ID, position, revision: 4,
    expect: { kind: 'answerable', number: null, typeId: null, keys: [], tolerance: '0' },
    lastCheck: null, note: null, createdAt, updatedAt: createdAt, archivedAt: null, ...overrides,
  };
}

function check(result: Check['result'], overrides: Partial<Check> = {}): Check {
  return {
    id: 'batch-check-1', questionId: 'cq-1', qaQuestionId: 'qa-1', release, stale: false,
    result, detail: null, createdAt, finishedAt: result === 'pending' ? null : createdAt, ...overrides,
  };
}

function listResponse(items: Question[], bulkRunning: boolean) {
  const response = jsonResponse({ items });
  response.headers.set('X-Cq-Check-Running', String(bulkRunning));
  return response;
}

function open(items: Question[], overrides: Record<string, RouteHandler> = {}, canEdit = true) {
  const api = mockApi({
    [`GET ${collection}`]: () => listResponse(items, false),
    [`GET ${collection}/coverage`]: () => ({ release, items: [] }),
    'GET /api/ontologies/:id/elements': () => [type],
    'GET /api/ontologies/:id/objects/types': () => ({ release, items: [] }),
    ...overrides,
  });
  renderWithProviders(<QuestionsPanel ontologyId={ONTOLOGY_ID} canEdit={canEdit} />);
  return api;
}

const button = (name: string) => screen.getByRole('button', { name });
const findButton = (name: string) => screen.findByRole('button', { name });
const field = (key: string, required = false) => within(screen.getByRole('dialog')).getByRole('textbox', {
  name: i18n.t(`cq.${key}`) + (required ? ' *' : ''),
});
const change = (input: HTMLElement, value: string) => fireEvent.change(input, { target: { value } });
const save = () => fireEvent.click(button(i18n.t('ontologyPage.edit.save')));
const tick = () => act(() => vi.advanceTimersByTimeAsync(2100));
afterEach(() => vi.useRealTimers());

it.each([true, false])('offers empty-state actions only to editors (canEdit=%s)', async (canEdit) => {
  open([], {}, canEdit);
  expect(await screen.findByText(i18n.t('cq.empty'))).toBeVisible();
  for (const key of ['create', 'import']) {
    expect(screen.queryAllByRole('button', { name: i18n.t(`cq.${key}`) }).length > 0).toBe(canEdit);
  }
  if (!canEdit) expect(screen.queryByRole('button')).toBeNull();
});

it('renders all results, old versions, coverage warnings and readable differences for viewers', async () => {
  const failed = question(4, {
    expect: { kind: 'objects', typeId: type.id, keys: ['W01'], number: null, tolerance: '0' },
    lastCheck: check('fail', { detail: { missing: ['W01'], extra: ['W02'], actual: '1', errorCode: null } }),
  });
  const number = question(7, {
    expect: { kind: 'number', typeId: null, keys: [], number: '0.91', tolerance: '0.01' },
    lastCheck: check('fail', { detail: { missing: [], extra: [], actual: '0.87', errorCode: null } }),
  });
  const items = [question(), question(2, { lastCheck: check('pending') }),
    question(3, { lastCheck: check('pass', { stale: true }) }), failed,
    question(5, { lastCheck: check('unanswerable') }), question(6, { lastCheck: check('error') }), number];
  open(items, { [`GET ${collection}/coverage`]: () => ({ release, items: [
    { questionId: failed.id, status: 'binding_missing', elements: [{ id: type.id, label: '钢卷', present: true, bound: false }] },
    { questionId: number.id, status: 'element_missing', elements: [] },
    { questionId: 'cq-1', status: 'never_checked', elements: [] },
  ] }) }, false);
  const table = within(await screen.findByRole('table'));
  expect(table.getByText(i18n.t('cq.unchecked'))).toBeVisible();
  for (const result of ['pending', 'pass', 'fail', 'unanswerable', 'error']) {
    expect(table.getAllByText(i18n.t(`cq.result.${result}`))[0]).toBeVisible();
  }
  expect(table.getByText(i18n.t('cq.oldVersion'))).toBeVisible();
  expect(table.getAllByText(i18n.t('cq.version', { version: 2 }))[0]).toBeVisible();
  expect(table.queryByRole('button')).toBeNull();
  const warning = (await screen.findByText(i18n.t('cq.coverage.title'))).parentElement!;
  expect(warning).toHaveTextContent(failed.text);
  expect(warning).toHaveTextContent(number.text);
  expect(warning).not.toHaveTextContent(items[0]!.text);
  const row = within(table.getByRole('row', { name: new RegExp(failed.text) }));
  expect(await row.findByText(i18n.t('cq.objectCount', { count: 1, type: '钢卷' }))).toBeVisible();
  fireEvent.click(row.getByText(i18n.t('cq.differences')));
  expect(row.getByText(/W01/)).toBeVisible();
  expect(row.getByText(/W02/)).toBeVisible();
  const numericRow = within(table.getByRole('row', { name: new RegExp(number.text) }));
  fireEvent.click(numericRow.getByText(i18n.t('cq.differences')));
  expect(numericRow.getByText(/0\.87/)).toBeVisible();
});

it('polls a single check to completion without disabling Check all', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const item = question();
  const api = open([item], { [`POST ${resource}/check`]: () => (item.lastCheck = check('pending')) });
  fireEvent.click(await findButton(i18n.t('cq.check')));
  expect(await screen.findByText(i18n.t('cq.result.pending'))).toBeVisible();
  expect(button(i18n.t('cq.checkAll'))).toBeEnabled();
  item.lastCheck = check('pass');
  await tick();
  expect(await screen.findByText(i18n.t('cq.result.pass'))).toBeVisible();
  const reads = api.calls('GET', collection).length;
  await tick();
  expect(api.calls('GET', collection)).toHaveLength(reads);
});

it.each(['start', 'restore', 'conflict'])('tracks a bulk check through completion (%s)', async (mode) => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const item = question();
  let running = mode === 'restore';
  const api = open([item], {
    [`GET ${collection}`]: () => listResponse([item], running),
    [`POST ${collection}/check`]: () => {
      running = true;
      item.lastCheck = check('pending');
      return mode === 'conflict' ? problemResponse(409, 'cq.check_running') : { checks: [item.lastCheck] };
    },
  });
  if (mode !== 'restore') {
    await screen.findByText(item.text);
    fireEvent.click(button(i18n.t('cq.checkAll')));
  }
  expect(await findButton(i18n.t('cq.checkingAll'))).toBeDisabled();
  if (mode === 'conflict') expect(await screen.findByText(i18n.t('cq.errors.cq.check_running'))).toBeVisible();
  running = false;
  item.lastCheck = check('pending', { id: 'independent-single-check' });
  await tick();
  expect(await findButton(i18n.t('cq.checkAll'))).toBeEnabled();
  expect(api.calls('POST', collection + '/check')).toHaveLength(mode === 'restore' ? 0 : 1);
});

it.each(['answerable', 'objects', 'number'] as const)('validates and saves a new %s expectation', async (kind) => {
  const api = open([], { [`POST ${collection}`]: () => question() });
  await screen.findByText(i18n.t('cq.empty'));
  fireEvent.click(screen.getAllByRole('button', { name: i18n.t('cq.create') })[0]!);
  const dialog = within(await screen.findByRole('dialog'));
  const text = field('text', true);
  change(text, '   ');
  save();
  expect(api.calls('POST', collection)).toHaveLength(0);
  expect(dialog.getByRole('alert')).toBeVisible();
  change(text, '钢卷合格吗？');
  change(field('note'), '质量验收');
  fireEvent.click(dialog.getByRole('radio', { name: i18n.t(`cq.kinds.${kind}`) }));
  let expected: components['schemas']['CqExpectInput'] = { kind };
  if (kind === 'objects') {
    await dialog.findByRole('option', { name: '钢卷' });
    change(dialog.getByRole('combobox'), type.id);
    change(field('keys'), Array.from({ length: 101 }, (_, n) => String(n)).join('\n'));
    save();
    expect(dialog.getByRole('alert')).toBeVisible();
    expect(api.calls('POST', collection)).toHaveLength(0);
    change(field('keys'), 'MES · W01\n["产线 · A","W02"]');
    expected = { kind, typeId: type.id, keys: ['MES · W01', '["产线 · A","W02"]'] };
  } else if (kind === 'number') {
    change(field('number', true), '0.9230769230769230769');
    change(field('tolerance'), '-1');
    save();
    expect(dialog.getByRole('alert')).toBeVisible();
    expect(api.calls('POST', collection)).toHaveLength(0);
    change(field('tolerance'), '');
    expected = { kind, number: '0.9230769230769230769', tolerance: '0' };
  }
  save();
  await waitFor(() => expect(api.calls('POST', collection).map((r) => r.body)).toEqual([
    { text: '钢卷合格吗？', note: '质量验收', expect: expected },
  ]));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});

it('prefills plain keys and keeps the edit open on a revision conflict', async () => {
  const user = userEvent.setup();
  const item = question(1, { expect: { kind: 'objects', typeId: type.id, keys: ['W01', 'W02'], number: null, tolerance: '0' } });
  const api = open([item], { [`PATCH ${resource}`]: () => problemResponse(409, 'cq.stale') });
  const row = within(await screen.findByRole('row', { name: new RegExp(item.text) }));
  await user.click(row.getByRole('button', { name: i18n.t('ontologyPage.moreActions') }));
  await user.click(await screen.findByRole('menuitem', { name: i18n.t('cq.edit') }));
  expect(field('keys')).toHaveValue('W01\nW02');
  change(field('note'), '更新备注');
  save();
  const dialog = within(await screen.findByRole('dialog'));
  expect(await dialog.findByText(i18n.t('cq.errors.cq.stale'))).toBeVisible();
  expect(field('note')).toHaveValue('更新备注');
  expect(api.calls('PATCH', resource)[0]?.body).toMatchObject({ revision: 4, note: '更新备注' });
});

it('moves only the chosen row and archives with its latest revision', async () => {
  const user = userEvent.setup();
  const item = question();
  const next = question(8);
  const items = [item, next];
  const api = open(items, {
    [`PATCH ${resource}`]: () => { next.position = 1; item.position = 8; item.revision++; return item; },
    [`POST ${resource}/archive`]: () => { items.splice(items.indexOf(item), 1); return item; },
  });
  const menu = async (key: string) => {
    const row = within(await screen.findByRole('row', { name: new RegExp(item.text) }));
    await user.click(row.getByRole('button', { name: i18n.t('ontologyPage.moreActions') }));
    await user.click(await screen.findByRole('menuitem', { name: i18n.t(`cq.${key}`) }));
  };
  await menu('moveDown');
  await waitFor(() => expect(screen.getAllByRole('row')[1]).toHaveTextContent(next.text));
  expect(api.requests.filter((r) => r.method === 'PATCH').map((r) => r.body)).toEqual([{ revision: 4, position: 8 }]);
  await menu('archive');
  await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: i18n.t('cq.archive') }));
  await waitFor(() => expect(screen.queryByText(item.text)).toBeNull());
  expect(api.calls('POST', resource + '/archive')[0]?.body).toEqual({ revision: 5 });
});

it('uploads TOML and reports import success and failure', async () => {
  const user = userEvent.setup();
  const content = '[[questions]]\ntext = "哪些钢卷需要复检？"';
  const bodies: string[] = [];
  open([], { [`POST ${collection}/import`]: async ({ request }) => {
    bodies.push(await request.text());
    return bodies.length === 1 ? { created: 1, skipped: 0 } : problemResponse(422, 'cq.invalid_import');
  } });
  await screen.findByText(i18n.t('cq.empty'));
  const picker = screen.getByLabelText(i18n.t('cq.importFile'));
  const file = new File([content], 'questions.toml', { type: 'text/plain' });
  await user.upload(picker, file);
  expect((await screen.findAllByText(i18n.t('cq.importResult', { created: 1, skipped: 0 })))[0]).toBeVisible();
  await user.upload(picker, file);
  expect(await screen.findByText(i18n.t('cq.errors.cq.invalid_import'))).toBeVisible();
  expect(bodies).toEqual([content, content]);
});
