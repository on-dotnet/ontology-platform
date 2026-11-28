import type { components } from '../src/api/schema';
import { csrfHeaders, expect, SEEDED_ONTOLOGIES, test } from './support';

test('AI pre-review flags a change without evidence and the reviewer rejects it with a reason', async ({ page }) => {
  const list = await page.request.get('/api/ontologies');
  await expect(list).toBeOK();
  const ontologies = await list.json() as components['schemas']['OntologySummary'][];
  const seedKey = SEEDED_ONTOLOGIES[0].key;
  const ontology = ontologies.find(({ key }) => key === seedKey);
  if (!ontology) throw new Error(`Missing seeded ontology: ${seedKey}`);

  const labelZh = '轧机';
  const saved = await page.request.post(`/api/ontologies/${ontology.id}/edits`, {
    headers: await csrfHeaders(page.request),
    data: {
      apply: false,
      items: [{ op: 'create', kind: 'entity_type', fields: { localName: 'RollingMill', labelZh, labelEn: 'Rolling mill' } }],
    } satisfies components['schemas']['EditRequest'],
  });
  await expect(saved).toBeOK();
  const { changeSetId, merged } = await saved.json() as components['schemas']['EditResult'];
  expect(merged).toBe(false);

  await page.goto(`/review/${changeSetId}`);
  await page.getByRole('button', { name: '✦ AI 预审', exact: true }).click();
  await expect(page.getByText('只做了规则检查', { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('有风险 1 · 建议拒绝 0 · 建议修改 0', { exact: true })).toBeVisible();

  const item = page.getByRole('article', { name: labelZh });
  await expect(item.getByRole('button', { name: '证据弱：没有资料证据', exact: true })).toBeVisible();
  const reason = '超出范围';
  await item.getByRole('button', { name: `带理由拒绝${labelZh}`, exact: true }).click();
  await page.getByRole('menuitem', { name: reason, exact: true }).click();
  await expect(item.getByRole('button', { name: '拒绝', exact: true, pressed: true })).toBeVisible();
  await expect(item.getByText(reason, { exact: true })).toBeVisible();
});
