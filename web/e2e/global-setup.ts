import { request, type FullConfig } from '@playwright/test';

import { credentials, SEEDED_ONTOLOGIES, STORAGE_STATE } from './support';

// Signs the test account in once through the API, seeds the ontologies the tests open, and saves
// the session for the signed-in tests. The stack is fresh on every run, so the seed always applies.
export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL;
  const api = await request.newContext({ baseURL });
  try {
    const login = await api.post('/api/auth/login', { data: credentials() });
    if (!login.ok()) throw new Error(`sign-in failed: ${login.status()} ${await login.text()}`);
    const { cookies } = await api.storageState();
    const csrf = cookies.find((cookie) => cookie.name === 'op_csrf')?.value;
    if (!csrf) throw new Error('sign-in set no op_csrf cookie');
    for (const ontology of SEEDED_ONTOLOGIES) {
      const created = await api.post('/api/ontologies', { data: ontology, headers: { 'X-CSRF-Token': csrf } });
      if (!created.ok()) throw new Error(`seeding ${ontology.key} failed: ${created.status()} ${await created.text()}`);
    }
    await api.storageState({ path: STORAGE_STATE });
  } finally {
    await api.dispose();
  }
}
