import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { UserInfo } from '@/features/auth/api';
import { changeSetFixture, elementFixture, elementRefFixture, impactFixture, itemFixture, ontologyFixture } from '@/test/fixtures';
import { mockApi, problemResponse, renderApp, testUser, userWithRole, type RouteHandler } from '@/test/utils';

import type { ChangeItem, ChangeSetDetail } from './api';

const REJECT = '/api/change-sets/cs-manual/reject';

const moltenSteel = elementFixture();
const ladle = elementFixture({ id: 'el-ladle', localName: 'Ladle', labelZh: '钢包', labelEn: 'Ladle', definitionZh: '盛装钢水的容器。' });
const holds = elementFixture({ id: 'el-holds', kind: 'relation_type', localName: 'holds', labelZh: '盛装', domainId: 'el-ladle', rangeId: 'el-molten-steel' });
const heldBy = elementFixture({ id: 'el-held-by', kind: 'relation_type', localName: 'heldBy', labelZh: '被盛装', inverseId: 'el-holds' });
const ladleShape = elementFixture({ id: 'el-ladle-shape', kind: 'constraint', localName: 'LadleShape', labelZh: '钢包校验', domainId: 'el-ladle' });

const manual = { confidence: null, rationale: null, evidence: [], tempRef: null };

function manualItems(): ChangeItem[] {
  return [
    itemFixture({ ...manual, id: 'item-new', proposed: { localName: 'Slab', labelZh: '板坯', labelEn: 'Slab', synonyms: [] } }),
    itemFixture({
      ...manual,
      id: 'item-ladle',
      seq: 2,
      op: 'update',
      targetElementId: 'el-ladle',
      proposed: { definitionZh: '盛装和运送钢水的容器。' },
      before: { localName: 'Ladle', labelZh: '钢包', labelEn: 'Ladle', definitionZh: '盛装钢水的容器。', synonyms: [], parentRef: null },
    }),
    itemFixture({
      ...manual,
      id: 'item-steel',
      seq: 3,
      op: 'delete',
      targetElementId: 'el-molten-steel',
      proposed: {},
      before: { localName: 'MoltenSteel', labelZh: '钢水', labelEn: 'Molten steel', synonyms: [], parentRef: null },
    }),
  ];
}

function manualChangeSet(overrides: Partial<ChangeSetDetail> = {}): ChangeSetDetail {
  return changeSetFixture(manualItems(), { id: 'cs-manual', title: '手工编辑', source: 'manual', documentId: null, createdBy: testUser.id, ...overrides });
}

interface ServerOptions {
  user?: UserInfo;
  reviewMode?: 'single' | 'separate';
  initial?: ChangeSetDetail;
  reject?: RouteHandler;
}

function submitterServer({ user, reviewMode = 'single', initial = manualChangeSet(), reject }: ServerOptions = {}) {
  let state = initial;
  return mockApi(
    {
      'GET /api/ontologies': () => [ontologyFixture({ openChangeSetCount: 1 })],
      'GET /api/settings/platform': () => ({ reviewMode }),
      'GET /api/change-sets': () => [state],
      'GET /api/change-sets/:id': () => state,
      'GET /api/ontologies/:id/elements': () => [moltenSteel, ladle, holds, heldBy, ladleShape],
      'GET /api/ontologies/:id/elements/:elementId/impact': ({ params }) =>
        params.elementId === 'el-molten-steel'
          ? impactFixture('el-molten-steel', {
              relations: [elementRefFixture(holds)],
              cascade: [
                { op: 'delete', element: elementRefFixture(holds) },
                { op: 'update', element: elementRefFixture(heldBy) },
              ],
            })
          : impactFixture(params.elementId ?? '', {
              relations: [elementRefFixture(holds)],
              constraints: [elementRefFixture(ladleShape)],
            }),
      'POST /api/change-sets/:id/reject':
        reject ??
        (() => {
          state = { ...state, status: 'rejected' };
          const { items: _items, ...summary } = state;
          return summary;
        }),
    },
    { user },
  );
}

function card(name: RegExp) {
  return screen.getByRole('article', { name });
}

describe('withdrawing a change set', () => {
  it('lets an editor withdraw a change set they submitted, after confirming', async () => {
    const user = userEvent.setup();
    const api = submitterServer({ user: userWithRole('editor') });
    renderApp('/review/cs-manual');

    const withdraw = await screen.findByRole('button', { name: '撤回' });
    expect(screen.getByText('只读')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '接受' })).not.toBeInTheDocument();

    await user.click(withdraw);
    const dialog = await screen.findByRole('dialog', { name: '撤回“手工编辑”？' });
    expect(dialog).toHaveTextContent('撤回后变更集变为已拒绝');
    await user.click(within(dialog).getByRole('button', { name: '撤回变更集' }));

    await waitFor(() => expect(api.calls('POST', REJECT)).toHaveLength(1));
    expect((await screen.findAllByText('已撤回变更集')).length).toBeGreaterThan(0);
    expect(await screen.findByText('已拒绝', { selector: 'span' })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('button', { name: '撤回' })).not.toBeInTheDocument());
  });

  it('keeps the change set open when withdrawing fails, and says why', async () => {
    const user = userEvent.setup();
    submitterServer({ user: userWithRole('editor'), reject: () => problemResponse(409, 'changeset.closed') });
    renderApp('/review/cs-manual');

    await user.click(await screen.findByRole('button', { name: '撤回' }));
    const dialog = await screen.findByRole('dialog', { name: '撤回“手工编辑”？' });
    await user.click(within(dialog).getByRole('button', { name: '撤回变更集' }));
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('没有撤回');
    expect(alert).toHaveTextContent('这个变更集已合并或已拒绝，不能再修改。');
  });

  it('is not offered for someone else’s change set', async () => {
    submitterServer({ user: userWithRole('editor'), initial: manualChangeSet({ createdBy: '00000000-0000-4000-8000-000000000999' }) });
    renderApp('/review/cs-manual');

    expect(await screen.findByRole('article', { name: /板坯/ })).toBeInTheDocument();
    expect(screen.getByText('只读')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '撤回' })).not.toBeInTheDocument();
  });

  it('is not offered to a reviewer who may review their own change set (single review mode)', async () => {
    submitterServer({ user: userWithRole('reviewer'), reviewMode: 'single' });
    renderApp('/review/cs-manual');

    expect(await screen.findByRole('button', { name: '合并到本体' })).toBeInTheDocument();
    expect(within(card(/板坯/)).getByRole('button', { name: '接受' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '撤回' })).not.toBeInTheDocument();
  });
});

describe('separate review mode', () => {
  it('shows a reviewer their own change set read-only, explains why, and lets them withdraw it', async () => {
    submitterServer({ user: userWithRole('reviewer'), reviewMode: 'separate' });
    renderApp('/review/cs-manual');

    expect(await screen.findByRole('button', { name: '撤回' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '只读' })).toHaveAccessibleDescription('异人审核模式下，你提交的变更集由其他审核人处理。');
    for (const name of ['接受', '拒绝', '合并到本体', /^接受全部/, /^修改“/]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
  });

  it('lets a reviewer review change sets others submitted', async () => {
    submitterServer({ user: userWithRole('reviewer'), reviewMode: 'separate', initial: manualChangeSet({ createdBy: '00000000-0000-4000-8000-000000000999' }) });
    renderApp('/review/cs-manual');

    expect(await screen.findByRole('button', { name: '合并到本体' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '撤回' })).not.toBeInTheDocument();
  });
});

describe('impact of updates and deletes', () => {
  it('loads the impact of an item only when asked: the cascade of a delete, the references of an update', async () => {
    const user = userEvent.setup();
    const api = submitterServer({ initial: manualChangeSet({ createdBy: null }) });
    renderApp('/review/cs-manual');

    const created = await screen.findByRole('article', { name: /板坯/ });
    const impactRequests = () => api.requests.filter((request) => request.path.endsWith('/impact'));
    expect(within(created).queryByRole('button', { name: '查看影响' })).not.toBeInTheDocument();
    expect(impactRequests()).toHaveLength(0);

    const deleted = card(/钢水/);
    const showDeleted = within(deleted).getByRole('button', { name: '查看影响' });
    expect(showDeleted).toHaveAttribute('aria-expanded', 'false');
    await user.click(showDeleted);
    const cascade = await within(deleted).findByRole('region', { name: '“钢水”的影响' });
    expect(await within(cascade).findByText('删除时会一并处理 2 个元素')).toBeInTheDocument();
    expect(within(within(cascade).getByRole('list', { name: '一并删除（1）' })).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      '关系盛装',
    ]);
    expect(within(within(cascade).getByRole('list', { name: '清除引用（1）' })).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      '关系被盛装清空互逆关系',
    ]);
    expect(impactRequests().map((request) => request.path)).toEqual(['/api/ontologies/onto-steel/elements/el-molten-steel/impact']);

    const updated = card(/钢包/);
    await user.click(within(updated).getByRole('button', { name: '查看影响' }));
    const references = await within(updated).findByRole('region', { name: '“钢包”的影响' });
    const list = await within(references).findByRole('list', { name: '被 2 个元素引用' });
    expect(within(list).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['关系盛装', '约束钢包校验']);
    expect(impactRequests()).toHaveLength(2);

    await user.click(within(updated).getByRole('button', { name: '收起影响' }));
    expect(within(updated).queryByRole('region', { name: '“钢包”的影响' })).not.toBeInTheDocument();
  });

  it('is not offered once the change set is closed', async () => {
    submitterServer({ initial: manualChangeSet({ createdBy: null, status: 'merged', mergedAt: '2026-11-21T08:00:00Z' }) });
    renderApp('/review/cs-manual');

    expect(await screen.findByRole('article', { name: /钢水/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '查看影响' })).not.toBeInTheDocument();
  });
});
