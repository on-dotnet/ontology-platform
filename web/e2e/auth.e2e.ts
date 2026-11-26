import { credentials, expect, SIGNED_OUT, SIGNED_OUT_CHECK, test } from './support';

test.use({ storageState: SIGNED_OUT, expectedFailedLoads: [SIGNED_OUT_CHECK] });

test('signed out, a page redirects to the sign-in form', async ({ page }) => {
  await page.goto('/ontology');
  await expect(page).toHaveURL(/\/login\?redirect=/);
  await expect(page.getByRole('heading', { level: 1, name: '登录' })).toBeVisible();
});

test('the test account signs in and lands on the workbench', async ({ page }) => {
  const { username, password } = credentials();
  await page.goto('/login');
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.locator('form button[type="submit"]').click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('navigation', { name: '主导航' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
});
