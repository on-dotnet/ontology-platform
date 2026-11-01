// 从g4-connections.openapi.json自动生成；运行pnpm generate:types，禁止手工编辑。

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type CatalogDiscoveryJobView = { "jobId": string; "connectionId": string; "configRevision": number; "status": string; "createdAtUtc": string; "completedAtUtc": null | string; "snapshotId": null | string; "traceId": string };

export type CatalogField = { "name": string; "nativeType": string; "nullable": boolean; "ordinal": number; "precision": null | number; "scale": null | number };

export type CatalogObject = { "schema": string; "name": string; "kind": string; "fields": Array<CatalogField> };

export type CatalogSnapshotListPage = { "items": Array<CatalogSnapshotView>; "nextCursor": null | string };

export type CatalogSnapshotView = { "snapshotId": string; "connectionId": string; "configRevision": number; "secretVersion": number; "scope": ResourceScope; "schemaFingerprint": string; "capturedAtUtc": string; "status": string; "objects": Array<CatalogObject> };

export type CommandContext = { "commandId": string; "idempotencyKey": string; "expectedRevision": number; "reason": string };

export type ConnectionConfig = ConnectionConfigPgConnectionConfig | ConnectionConfigOracleConnectionConfig | ConnectionConfigDorisConnectionConfig | ConnectionConfigTdengineConnectionConfig | ConnectionConfigWebApiConnectionConfig;

export type ConnectionConfigDorisConnectionConfig = { "type": "DORIS"; "profile": DorisConnectionProfile };

export type ConnectionConfigOracleConnectionConfig = { "type": "ORACLE"; "profile": OracleConnectionProfile };

export type ConnectionConfigPgConnectionConfig = { "type": "POSTGRESQL"; "profile": PgConnectionProfile };

export type ConnectionConfigTdengineConnectionConfig = { "type": "TDENGINE"; "profile": TdengineConnectionProfile };

export type ConnectionConfigWebApiConnectionConfig = { "type": "WEB_API"; "profile": WebApiConnectionProfile };

export type ConnectionCreateRequest = { "displayName": string; "scopeSelection": ResourceScope; "config": ConnectionConfig; "secretRef": null | string; "command": CommandContext };

export type ConnectionDraftProbeRequest = { "scopeSelection": ResourceScope; "config": ConnectionConfig; "secretRef": string; "command": CommandContext };

export type ConnectionListPage = { "items": Array<ConnectionView>; "nextCursor": null | string };

export type ConnectionMutationCommand = { "command": CommandContext };

export type ConnectionPatchRequest = { "displayName"?: null | string; "scopeSelection"?: null | ResourceScope; "config"?: null | ConnectionConfig; "command": CommandContext };

export type ConnectionProbeStage = { "name": string; "status": string; "durationMs": number; "diagnosticCode": null | string };

export type ConnectionProbeView = { "probeId": string; "connectionId": null | string; "configHash": string; "secretVersion": number; "scope": ResourceScope; "status": string; "stages": Array<ConnectionProbeStage>; "startedAtUtc": string; "completedAtUtc": null | string; "expiresAtUtc": string; "traceId": string; "stale": boolean };

export type ConnectionRotateSecretRequest = { "secretRef": string; "command": CommandContext };

export type ConnectionSecretIntakeRequest = { "secretValue": string; "scopeSelection": ResourceScope; "purpose": string; "command": CommandContext };

export type ConnectionView = { "id": string; "displayName": string; "scope": ResourceScope; "config": ConnectionConfig; "configRevision": number; "state": string; "secretConfigured": boolean; "secretVersion": number; "probeFresh": boolean; "lastProbeId": null | string; "updatedAtUtc": string };

export type DorisConnectionProfile = { "feHost": string; "queryPort": number; "catalog": string; "database": string; "username": string; "tls": boolean };

export type OracleConnectionProfile = { "host": string; "port": number; "serviceName": string; "username": string; "tls": boolean; "allowedOwners": Array<string> };

export type PgConnectionProfile = { "host": string; "port": number; "database": string; "username": string; "sslMode": string; "allowedSchemas": Array<string> };

export type ResourceScope = { "organizationId": string; "siteIds": Array<string> };

export type SecretIntakeReceipt = { "secretRef": string; "expiresAtUtc": string; "usageLimit": number; "credentialVersion": number };

export type TdengineConnectionProfile = { "wsUrl": string; "database": string; "timePrecision": string; "timeZone": null | string };

export type WebApiConnectionProfile = { "baseOrigin": string; "operationId": string; "method": string; "approvedPath": string; "authentication": string; "pagination": string; "hostPolicyRef": string };
