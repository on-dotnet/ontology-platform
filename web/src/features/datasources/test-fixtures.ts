import type { components } from '@/api/schema';

type DataSource = components['schemas']['DataSource'];

export function makeSource(overrides: Partial<DataSource> = {}): DataSource {
  const at = '2026-11-20T08:00:00Z';
  return {
    id: '00000000-0000-4000-8000-000000000009',
    name: '冶金样例',
    kind: 'postgresql',
    status: 'active',
    connection: { host: 'db.example.test', port: 5432, database: 'steel', username: 'reader', sslMode: 'prefer', schemas: ['steel'] },
    hasCredential: true,
    credentialUpdatedAt: at,
    allowSamples: false,
    lastTest: null,
    catalog: { status: 'never', refreshedAt: null, errorCode: null, tableCount: 0 },
    boundTypeCount: null,
    revision: 3,
    createdAt: at,
    updatedAt: at,
    ...overrides,
  };
}
