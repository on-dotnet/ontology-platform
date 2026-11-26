import { fireEvent, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';

import i18n from '@/i18n';
import { renderApp } from '@/test/utils';

import { answer, answered, evidence, qaServer } from './test-fixtures';

it('shows conclusion, facts, assumptions and counterpoints with separate evidence tables', async () => {
  qaServer([answered]);
  renderApp('/explore?tab=ask');
  expect(await screen.findByText(answer.text!)).toBeVisible();
  for (const key of ['conclusion', 'facts', 'assumptions', 'counterpoints']) {
    expect(screen.getByRole('heading', { name: i18n.t(`qa.${key}`) })).toBeVisible();
  }
  for (const value of ['2', '97.5%', '一号钢卷', '0', '仅统计已完成的检验。', '同一卷可能有多条记录。']) {
    expect(screen.getByText(value)).toBeVisible();
  }
  const toggle = screen.getByText(i18n.t('qa.evidence.title'));
  expect(screen.queryByRole('table')).toBeNull();
  fireEvent.click(toggle);
  const rows = screen.getByRole('table', { name: i18n.t('qa.evidence.rows') });
  const tail = screen.getByRole('table', { name: i18n.t('qa.evidence.tail') });
  expect(within(rows).getByText('W2401')).toBeVisible();
  expect(within(rows).getByText('Q235B')).toBeVisible();
  expect(within(rows).queryByText('TEST-07')).toBeNull();
  expect(within(tail).getByText('TEST-07')).toBeVisible();
  expect(within(tail).queryByText('W2401')).toBeNull();
  for (const key of ['elements', 'bindings', 'steps', 'documents']) {
    expect(screen.getByRole('heading', { name: i18n.t(`qa.evidence.${key}`) })).toBeVisible();
  }
  for (const value of ['mes.coil', 'number', '是否合格 = 否', '复检须由质量组确认。', '依据版本 v3']) {
    expect(screen.getByText(value)).toBeVisible();
  }
});

it.each([
  ['rows_not_shared', 'rowsNotShared'], ['answer_unavailable', 'answerUnavailable'],
  ['cited_unknown', 'citedUnknown'], ['rows_truncated', 'rowsTruncated'],
] as const)('explains %s and keeps facts and evidence available', async (note, key) => {
  qaServer([{ ...answered, plan: null,
    answer: { ...answer, text: null, notes: [note], counterpoints: [] },
    evidence: { ...evidence, tail: [] },
  }]);
  renderApp('/explore?tab=ask');
  expect(await screen.findByText(i18n.t(`qa.${key}`))).toBeVisible();
  for (const section of ['conclusion', 'assumptions', 'counterpoints']) {
    expect(screen.queryByRole('heading', { name: i18n.t(`qa.${section}`) })).toBeNull();
  }
  expect(screen.getByText('一号钢卷')).toBeVisible();
  fireEvent.click(screen.getByText(i18n.t('qa.evidence.title')));
  expect(screen.getByRole('table', { name: i18n.t('qa.evidence.rows') })).toHaveTextContent('W2401');
  expect(screen.queryByText(i18n.t('qa.evidence.tail'))).toBeNull();
});

it('shows the truncation notice from evidence even when answer notes are empty', async () => {
  qaServer([{ ...answered, evidence: { ...evidence, truncated: true } }]);
  renderApp('/explore?tab=ask');
  expect(await screen.findByText(i18n.t('qa.rowsTruncated'))).toBeVisible();
});
