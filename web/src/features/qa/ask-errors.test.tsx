import { fireEvent, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

import i18n from '@/i18n';
import { formatDateTime } from '@/lib/format';
import { ONTOLOGY_ID } from '@/test/fixtures';
import { problemResponse, renderApp } from '@/test/utils';

import { listPath, qaServer, queued } from './test-fixtures';

async function submit() {
  const field = await screen.findByRole('textbox', { name: i18n.t('qa.question') });
  fireEvent.change(field, { target: { value: queued.question } });
  fireEvent.click(screen.getByRole('button', { name: i18n.t('qa.ask') }));
}

it.each(['GET', 'POST'])('replaces the panel with a release link after %s reports query.no_release', async (method) => {
  qaServer([], { [`${method} ${listPath}`]: () => problemResponse(409, 'query.no_release') });
  renderApp('/explore?tab=ask');
  if (method === 'POST') await submit();
  expect(await screen.findByText(i18n.t('qa.errors.query.no_release'))).toBeVisible();
  expect(screen.getByRole('link', { name: i18n.t('qa.publish') })).toHaveAttribute('href', `/releases?ontology=${ONTOLOGY_ID}`);
  expect(screen.queryByRole('textbox', { name: i18n.t('qa.question') })).toBeNull();
});

it.each(['status', 'submission'])('disables asking when %s reports an unconfigured AI', async (source) => {
  qaServer([], source === 'status'
    ? { 'GET /api/ai/status': () => ({ configured: false, reachable: null, model: null }) }
    : { [`POST ${listPath}`]: () => problemResponse(409, 'ai.not_configured') });
  renderApp('/explore?tab=ask');
  if (source === 'submission') await submit();
  expect(await screen.findByText(i18n.t('qa.errors.ai.not_configured'))).toBeVisible();
  expect(screen.getByRole('textbox', { name: i18n.t('qa.question') })).toBeDisabled();
  expect(screen.getByRole('button', { name: i18n.t('qa.ask') })).toBeDisabled();
  expect(screen.getByRole('link', { name: i18n.t('qa.settings') })).toHaveAttribute('href', '/settings');
});

it.each(['120', 'Wed, 02 Dec 2026 12:30:00 GMT'])('localizes the rate limit with Retry-After %s', async (header) => {
  const now = Date.parse('2026-12-02T11:00:00Z');
  vi.spyOn(Date, 'now').mockReturnValue(now);
  const retryAt = new Date(header === '120' ? now + 120_000 : Date.parse(header)).toISOString();
  qaServer([], { [`POST ${listPath}`]: () => {
    const response = problemResponse(429, 'qa.rate_limited');
    response.headers.set('Retry-After', header);
    return response;
  } });
  renderApp('/explore?tab=ask');
  await submit();
  const notice = await screen.findByRole('alert');
  expect(notice).toHaveTextContent(i18n.t('qa.errors.qa.rate_limited', { time: formatDateTime(retryAt, i18n.language) }));
});

it.each([['ai.invalid_output', 'qa.errors.ai.invalid_output'], ['unknown.failure', 'errors.unknown']] as const)(
  'localizes the submission error %s inside the form', async (code, key) => {
    qaServer([], { [`POST ${listPath}`]: () => problemResponse(409, code) });
    renderApp('/explore?tab=ask');
    await submit();
    const form = within(screen.getByRole('form', { name: i18n.t('qa.question') }));
    expect(await form.findByRole('alert')).toHaveTextContent(i18n.t(key));
    expect(form.getByRole('textbox')).toHaveValue(queued.question);
  },
);

it('uses a localized fallback and allows retry for an unknown failure code', async () => {
  qaServer([{ ...queued, status: 'failed', errorCode: 'unknown.failure' }]);
  renderApp('/explore?tab=ask');
  expect(await screen.findByText(i18n.t('errors.unknown'))).toBeVisible();
  expect(screen.getByRole('button', { name: i18n.t('qa.retry') })).toBeEnabled();
});
