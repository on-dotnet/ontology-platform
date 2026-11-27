import type { components } from '@/api/schema';

import type { DataSource } from './api';

type Create = components['schemas']['DataSourceCreate'];
type Patch = components['schemas']['DataSourcePatch'];
type TestRequest = components['schemas']['ConnectionTestRequest'];

export const sslModes = ['disable', 'prefer', 'require', 'verify-full'] as const satisfies readonly Create['sslMode'][];

interface SchemaRow {
  id: number;
  name: string;
  exact?: boolean;
}

// PostgreSQL identifiers can contain surrounding spaces. Only trim free-text input.
export function schemaName(row: SchemaRow) {
  return row.exact ? row.name : row.name.trim();
}

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
    schemas: schemas.map((name, id): SchemaRow => ({ id, name, exact: true })),
    allowSamples: source?.allowSamples ?? false,
  };
}

export type SourceForm = ReturnType<typeof initialForm>;
export type TextField = 'name' | 'host' | 'port' | 'database' | 'username' | 'password';
export type Operation = 'test' | 'save';

export function validationErrors(form: SourceForm, passwordRequired: boolean, operation: Operation) {
  const errors: Partial<Record<TextField, 'required' | 'invalidPort'>> = {};
  if (operation === 'save' && !form.name.trim()) errors.name = 'required';
  if (!form.host.trim()) errors.host = 'required';
  const port = Number(form.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) errors.port = 'invalidPort';
  if (!form.database.trim()) errors.database = 'required';
  if (!form.username.trim()) errors.username = 'required';
  if (passwordRequired && !form.password) errors.password = 'required';
  return errors;
}

function connectionTarget(form: SourceForm, source?: DataSource) {
  return {
    host: form.host.trim(),
    port: Number(form.port),
    // An untouched PostgreSQL username can include significant surrounding spaces.
    username: form.username === source?.connection?.username ? form.username : form.username.trim(),
    sslMode: form.sslMode,
  };
}

export function connectionTargetChanged(form: SourceForm, source?: DataSource) {
  const saved = source?.connection;
  if (!saved) return false;
  const target = connectionTarget(form, source);
  return target.host.toLowerCase() !== saved.host.trim().toLowerCase()
    || target.port !== saved.port || target.username !== saved.username || target.sslMode !== saved.sslMode;
}

function connectionFields(form: SourceForm, source?: DataSource) {
  return {
    ...connectionTarget(form, source),
    database: form.database.trim(),
    schemas: form.schemas.map(schemaName).filter((name) => name.length > 0),
  };
}

export function testRequest(form: SourceForm, source?: DataSource): TestRequest {
  return {
    kind: 'postgresql',
    ...connectionFields(form, source),
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
  const connection = connectionFields(form, source);
  const previous = source.connection;
  const name = form.name.trim();
  if (form.name !== source.name && name !== source.name) patch.name = name;
  // Older sources may contain padding. Normalize a field only when the user edits it.
  for (const field of ['host', 'database', 'username'] as const) {
    if (form[field] !== previous?.[field] && connection[field] !== previous?.[field]) patch[field] = connection[field];
  }
  if (connection.port !== previous?.port) patch.port = connection.port;
  if (connection.sslMode !== previous?.sslMode) patch.sslMode = connection.sslMode;
  const savedSchemas = previous?.schemas ?? [];
  const matchesSaved = (names: string[]) =>
    names.length === savedSchemas.length && names.every((schema, index) => schema === savedSchemas[index]);
  if (!matchesSaved(form.schemas.map((row) => row.name)) && !matchesSaved(connection.schemas)) {
    patch.schemas = connection.schemas;
  }
  if (form.allowSamples !== source.allowSamples) patch.allowSamples = form.allowSamples;
  if (form.password) patch.password = form.password;
  return patch;
}
