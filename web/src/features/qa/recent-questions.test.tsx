import { fireEvent, screen } from '@testing-library/react';
import { expect, it } from 'vitest';

import i18n from '@/i18n';
import { ONTOLOGY_ID, ontologyFixture } from '@/test/fixtures';
import { renderApp } from '@/test/utils';

import { listPath, qaServer } from './test-fixtures';

it('fills the ask form from the selected ontology’s first three competency questions in position order', async () => {
  const id = 'onto-other';
  window.localStorage.setItem('op.explore.ontology', id);
  const api = qaServer([], {
    'GET /api/ontologies': () => [ontologyFixture(), ontologyFixture({ id, name: '质量' })],
    [`GET /api/ontologies/${id}/qa/questions`]: () => ({ items: [], nextCursor: null }),
    [`GET /api/ontologies/${id}/competency-questions`]: () => ({
      items: [4, 1, 3, 2].map((n) => ({ id: String(n), position: n, text: `问钢卷 ${n}` })),
    }),
  });
  renderApp('/explore?tab=ask');
  await screen.findByRole('button', { name: '问钢卷 1' });
  expect(screen.getAllByRole('button', { name: /问钢卷/ }).map((el) => el.textContent)).toEqual(['问钢卷 1', '问钢卷 2', '问钢卷 3']);
  expect(screen.queryByRole('button', { name: i18n.t('qa.example') })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '问钢卷 2' }));
  expect(screen.getByRole('textbox', { name: i18n.t('qa.question') })).toHaveValue('问钢卷 2');
  expect(api.calls('GET', `/api/ontologies/${ONTOLOGY_ID}/competency-questions`)).toHaveLength(0);
  expect(api.calls('POST', listPath)).toHaveLength(0);
  expect(api.calls('POST', `/api/ontologies/${id}/qa/questions`)).toHaveLength(0);
});
