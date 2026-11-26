import type { Page } from '@playwright/test';

import { expect, SEEDED_ONTOLOGIES, test } from './support';

const target = SEEDED_ONTOLOGIES[1];

/** Opens the ontology section from the sidebar and switches to the target ontology; returns its id. */
async function enterTargetOntology(page: Page): Promise<string> {
  await page.goto('/');
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '本体' }).click();
  await expect(page.getByRole('heading', { level: 1, name: '本体' })).toBeVisible();
  const selector = page.getByLabel('本体', { exact: true });
  await expect(selector.getByRole('option', { name: target.name })).toBeAttached();
  await selector.selectOption({ label: target.name });
  await expect(page).toHaveURL(/[?&]ontology=[0-9a-f-]{36}/);
  const id = new URL(page.url()).searchParams.get('ontology');
  if (!id) throw new Error('no ontology in the URL');
  return id;
}

test('the ontology list offers the seeded ontologies and one can be entered', async ({ page }) => {
  await enterTargetOntology(page);
  const selector = page.getByLabel('本体', { exact: true });
  for (const { name } of SEEDED_ONTOLOGIES) await expect(selector.getByRole('option', { name })).toBeAttached();
  await expect(selector.locator('option:checked')).toHaveText(target.name);
  await expect(page.getByText('当前版本')).toBeVisible();
});

test('the review page opens for the entered ontology', async ({ page }) => {
  const id = await enterTargetOntology(page);
  // The sidebar links do not carry ?ontology=, so the review page is opened for it directly.
  await page.goto(`/review?ontology=${id}`);
  await expect(page.getByRole('heading', { level: 1, name: '审核' })).toBeVisible();
  await expect(page.getByLabel('本体', { exact: true }).locator('option:checked')).toHaveText(target.name);
  await expect(page.getByText('这个本体还没有变更集')).toBeVisible();
});

test.describe('explore', () => {
  // The seeded ontologies have no release: the api answers 409 query.no_release by design and the
  // page turns that into its empty state.
  test.use({ expectedFailedLoads: [{ status: 409, path: /^\/api\/ontologies\/[0-9a-f-]{36}\/objects\/types$/ }] });

  test('the explore page opens', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '探索' }).click();
    await expect(page.getByRole('heading', { level: 1, name: '探索' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: '本体还没有发布版本' })).toBeVisible();
  });
});
