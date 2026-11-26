import type { components } from '@/api/schema';

import type { DataSource } from './api';

type Create = components['schemas']['DataSourceCreate'];
type Patch = components['schemas']['DataSourcePatch'];
type TestRequest = components['schemas']['ConnectionTestRequest'];

export const sslModes = ['disable', 'prefer', 'require', 'verify-full'] as const satisfies readonly Create['sslMode'][];

export function initialForm(source?: DataSource) {
  const connection = source?.connection;
  const schemas = connection?.schemas.length ? connection.schemas : [''];
  return {
    name: source?.name ?? '',
    host: connection?.host ?? '',
    port: String(connection?.port ?? 5432),
    database: connection?.database ?? '',
    username: connection?.username ?? '',
    password: '',
    sslMode: connection?.sslMode ?? 'prefer',
    schemas: schemas.map((name, id) => ({ id, name })),
    allowSamples: source?.allowSamples ?? false,
  };
}

export type SourceForm = ReturnType<typeof initialForm>;
export type TextField = 'name' | 'host' | 'port' | 'database' | 'username' | 'password';
export type Operation = 'test' | 'save';

export function validationErrors(form: SourceForm, editing: boolean, operation: Operation) {
  const errors: Partial<Record<TextField, 'required' | 'invalidPort'>> = {};
  if (operation === 'save' && !form.name.trim()) errors.name = 'required';
  if (!form.host.trim()) errors.host = 'required';
  const port = Number(form.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) errors.port = 'invalidPort';
  if (!form.database) errors.database = 'required';
  if (!form.username) errors.username = 'required';
  if (!editing && !form.password) errors.password = 'required';
  return errors;
}

function connectionFields(form: SourceForm) {
  return {
    host: form.host.trim(),
    port: Number(form.port),
    database: form.database,
    username: form.username,
    sslMode: form.sslMode,
    schemas: form.schemas.map((row) => row.name).filter((name) => name.length > 0),
  };
}

export function testRequest(form: SourceForm, source?: DataSource): TestRequest {
  return {
    kind: 'postgresql',
    ...connectionFields(form),
    ...(source && !form.password ? { dataSourceId: source.id } : { password: form.password }),
  };
}

export function createRequest(form: SourceForm): Create {
  return {
    kind: 'postgresql',
    ...connectionFields(form),
    name: form.name.trim(),
    password: form.password,
    allowSamples: form.allowSamples,
  };
}

export function patchRequest(form: SourceForm, source: DataSource): Patch {
  const patch: Patch = { revision: source.revision };
  const connection = connectionFields(form);
  const previous = source.connection;
  const name = form.name.trim();
  if (name !== source.name) patch.name = name;
  if (connection.host !== previous?.host) patch.host = connection.host;
  if (connection.port !== previous?.port) patch.port = connection.port;
  if (connection.database !== previous?.database) patch.database = connection.database;
  if (connection.username !== previous?.username) patch.username = connection.username;
  if (connection.sslMode !== previous?.sslMode) patch.sslMode = connection.sslMode;
  if (connection.schemas.length !== previous?.schemas.length ||
      connection.schemas.some((schema, index) => schema !== previous.schemas[index])) {
    patch.schemas = connection.schemas;
  }
  if (form.allowSamples !== source.allowSamples) patch.allowSamples = form.allowSamples;
  if (form.password) patch.password = form.password;
  return patch;
}
