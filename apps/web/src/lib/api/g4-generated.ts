// 从g4-connections.openapi.json自动生成；运行pnpm generate:types，禁止手工编辑。

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type CatalogDiscoveryJobView = { "jobId": string; "connectionId": string; "configRevision": number; "status": string; "createdAtUtc": string; "completedAtUtc": null | string; "snapshotId": null | string; "traceId": string };

export type CatalogField = { "name": string; "nativeType": string; "nullable": boolean; "ordinal": number; "precision": null | number; "scale": null | number; "oracleMetadata"?: null | OracleColumnMetadata };

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

export type JsonElement = JsonValue;

export type MappingActivationCheck = { "checkId": string; "proposalId": string; "bindingHash": string; "assessmentId": string; "checkedBinding": MappingVersionBinding; "checkedAtUtc": string; "expiresAtUtc": string; "stages": Array<MappingStageResult>; "semanticResultHash": string; "evidenceHash": string };

export type MappingActivationReceipt = { "activationId": string; "mappingId": string; "proposalId": string; "kind": "PUBLISH" | "ROLLBACK"; "mappingReleaseId": string; "manifestHash": string; "previousReleaseId": null | string; "activationRevision": number; "auditId": string; "outboxEventId": string; "activatedAtUtc": string };

export type MappingActivationRequest = { "bindingHash": string; "expectedActive": MappingExpectedActive; "command": CommandContext };

export type MappingActiveView = { "mappingId": string; "mappingReleaseId": string; "manifestHash": string; "activationRevision": number; "usable": boolean; "reasonCodes": Array<string> };

export type MappingAssessmentView = { "schemaVersion": "g4.mapping.v1"; "assessmentId": string; "mappingId": string; "target": MappingValidationTarget; "binding": MappingVersionBinding; "expectedActive": MappingExpectedActive; "stages": Array<MappingStageResult>; "issues": Array<MappingIssue>; "status": "READY_FOR_PROPOSAL" | "BLOCKED"; "semanticResultHash": string; "evidenceHash": string; "startedAtUtc": string; "finishedAtUtc": string; "expiresAtUtc": string };

export type MappingCommandRequest = { "command": CommandContext };

export type MappingConversion = { "id": string; "registeredId": "identity" | "decimal-scale-exact" | "celsius-to-kelvin" | "json-top-level-scalar"; "version": "1"; "parameters": JsonElement };

export type MappingDatasetRef = { "snapshotId": string; "schema": string; "name": string; "kind": "TABLE" };

export type MappingDecision = { "decidedBy": string; "decidedAtUtc": string; "decision": "APPROVE" | "REJECT"; "reason": string; "bindingHash": string };

export type MappingDecisionRequest = { "decision": "APPROVE" | "REJECT"; "bindingHash": string; "command": CommandContext };

export type MappingDefinition = { "entities": Array<MappingEntityBinding>; "properties": Array<MappingPropertyBinding>; "relations": Array<MappingRelationBinding>; "identitySpecs": Array<MappingIdentitySpec>; "temporalSpecs": Array<MappingTemporalSpec>; "conversions": Array<MappingConversion>; "unitSpecs": Array<MappingUnitSpec> };

export type MappingDifference = { "path": string; "beforeExists": boolean; "afterExists": boolean; "before": null | JsonElement; "after": null | JsonElement };

export type MappingDiffView = { "mappingId": string; "fromHash": string; "toHash": string; "changes": Array<MappingDifference> };

export type MappingDraftCreateRequest = { "scope": ResourceScope; "ontologyReleaseId": string; "ontologyManifestHash": string; "sourceConnectionId": string; "sourceCatalogSnapshotId": string; "mapping": MappingDefinition; "command": CommandContext };

export type MappingDraftPatchRequest = { "mapping": MappingDefinition; "command": CommandContext };

export type MappingDraftView = { "schemaVersion": "g4.mapping.v1"; "mappingId": string; "draftId": string; "scope": ResourceScope; "ontologyReleaseId": string; "ontologyManifestHash": string; "sourceConnectionId": string; "sourceCatalogSnapshotId": string; "revision": number; "mappingHash": string; "mapping": MappingDefinition; "status": "DRAFT" | "NEEDS_REVIEW" | "VALIDATING" | "READY_FOR_PROPOSAL" | "BLOCKED"; "updatedAtUtc": string };

export type MappingEntityBinding = { "id": string; "entityClassIri": string; "datasetRef": MappingDatasetRef; "identitySpecId": string; "temporalSpecId": string; "scopeFields": MappingScopeFields };

export type MappingExpectedActive = { "releaseId": null | string; "activationRevision": number };

export type MappingFieldRef = { "datasetRef": MappingDatasetRef; "ordinal": number; "name": string };

export type MappingIdentitySpec = { "id": string; "organizationFieldRef": MappingFieldRef; "siteFieldRef": MappingFieldRef; "sourceNamespace": string; "externalIdFieldRefs": Array<MappingFieldRef>; "validFromFieldRef": null | MappingFieldRef; "validToFieldRef": null | MappingFieldRef };

export type MappingIssue = { "code": string; "bindingId": null | string; "fieldRef": null | MappingFieldRef };

export type MappingJobView = { "jobId": string; "mappingId": string; "revision": number; "target": MappingValidationTarget; "status": "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED"; "assessmentId": null | string; "issueCodes": Array<string>; "createdAtUtc": string; "completedAtUtc": null | string };

export type MappingJoinFieldPair = { "from": MappingFieldRef; "to": MappingFieldRef };

export type MappingListItem = { "mappingId": string; "scope": ResourceScope; "revision": number; "status": "DRAFT" | "NEEDS_REVIEW" | "VALIDATING" | "READY_FOR_PROPOSAL" | "BLOCKED"; "activeReleaseId": null | string };

export type MappingPageOfMappingActivationCheck = { "items": Array<MappingActivationCheck>; "nextCursor": null | string };

export type MappingPageOfMappingAssessmentView = { "items": Array<MappingAssessmentView>; "nextCursor": null | string };

export type MappingPageOfMappingListItem = { "items": Array<MappingListItem>; "nextCursor": null | string };

export type MappingPageOfMappingProposalView = { "items": Array<MappingProposalView>; "nextCursor": null | string };

export type MappingPageOfMappingReleaseView = { "items": Array<MappingReleaseView>; "nextCursor": null | string };

export type MappingPropertyBinding = { "id": string; "entityBindingId": string; "propertyIri": string; "fieldRef": MappingFieldRef; "conversionId": null | string; "unitSpecId": null | string; "nullPolicy": "KEEP_NULL" | "REJECT_NULL" };

export type MappingProposalCreateRequest = MappingProposalCreateRequestMappingPublishProposalRequest | MappingProposalCreateRequestMappingRollbackProposalRequest;

export type MappingProposalCreateRequestMappingPublishProposalRequest = { "kind": "PUBLISH"; "draftId": string; "draftRevision": number; "schemaVersion": "g4.mapping.v1"; "scope": ResourceScope; "binding": MappingVersionBinding; "expectedActive": MappingExpectedActive; "expiresAtUtc": string; "command": CommandContext };

export type MappingProposalCreateRequestMappingRollbackProposalRequest = { "kind": "ROLLBACK"; "targetReleaseId": string; "manifestHash": string; "schemaVersion": "g4.mapping.v1"; "scope": ResourceScope; "binding": MappingVersionBinding; "expectedActive": MappingExpectedActive; "expiresAtUtc": string; "command": CommandContext };

export type MappingProposalView = MappingProposalViewMappingPublishProposalView | MappingProposalViewMappingRollbackProposalView;

export type MappingProposalViewMappingPublishProposalView = { "kind": "PUBLISH"; "draftId": string; "draftRevision": number; "schemaVersion": "g4.mapping.v1"; "proposalId": string; "mappingId": string; "proposalRevision": number; "scope": ResourceScope; "binding": MappingVersionBinding; "expectedActive": MappingExpectedActive; "submittedBy": string; "submittedAtUtc": string; "expiresAtUtc": string; "status": "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED" | "STALE" | "EXPIRED"; "decision": null | MappingDecision; "bindingHash": string; "activation": null | MappingActivationReceipt };

export type MappingProposalViewMappingRollbackProposalView = { "kind": "ROLLBACK"; "targetReleaseId": string; "manifestHash": string; "schemaVersion": "g4.mapping.v1"; "proposalId": string; "mappingId": string; "proposalRevision": number; "scope": ResourceScope; "binding": MappingVersionBinding; "expectedActive": MappingExpectedActive; "submittedBy": string; "submittedAtUtc": string; "expiresAtUtc": string; "status": "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED" | "STALE" | "EXPIRED"; "decision": null | MappingDecision; "bindingHash": string; "activation": null | MappingActivationReceipt };

export type MappingRelationBinding = { "id": string; "fromBindingId": string; "toBindingId": string; "predicateIri": string; "joinFieldPairs": Array<MappingJoinFieldPair>; "cardinality": "ONE_TO_MANY" | "MANY_TO_MANY"; "temporalJoinPolicy": "HALF_OPEN_OVERLAP" };

export type MappingReleaseManifest = { "schemaVersion": "g4.mapping.v1"; "mappingReleaseId": string; "mappingId": string; "scope": ResourceScope; "originDraftId": string; "originDraftRevision": number; "binding": MappingVersionBinding; "mapping": MappingDefinition; "reviewReceipt": MappingReviewReceipt; "createdAtUtc": string };

export type MappingReleaseProjection = { "currentDraftRevision": number; "active": boolean; "activationRevision": number; "usable": boolean; "reasonCodes": Array<string>; "observedAtUtc": string };

export type MappingReleaseView = { "manifest": MappingReleaseManifest; "manifestHash": string; "readOnly": boolean; "projection": MappingReleaseProjection };

export type MappingReviewReceipt = { "proposalId": string; "bindingHash": string; "submittedBy": string; "decidedBy": string; "decidedAtUtc": string };

export type MappingScopeFields = { "organization": MappingFieldRef; "site": MappingFieldRef };

export type MappingStageResult = { "stage": "SCHEMA" | "IDENTITY" | "TIME_UNIT" | "SECURITY" | "EXECUTABILITY" | "RECONCILIATION" | "IMPACT"; "status": "PASS" | "FAIL" | "INDETERMINATE" | "NOT_RUN"; "issueCodes": Array<string>; "evidenceHash": string };

export type MappingSuggestionCandidate = { "fieldRef": MappingFieldRef; "targetIri": string; "evidence": "METADATA" | "TERM" | "USER_ASSERTION" | "NO_EVIDENCE"; "status": "CANDIDATE_ONLY" };

export type MappingSuggestionRequest = { "mode": "OFF"; "command": CommandContext };

export type MappingSuggestionView = { "revision": number; "candidates": Array<MappingSuggestionCandidate>; "issueCodes": Array<string> };

export type MappingTemporalSpec = { "id": string; "eventTimeFieldRef": null | MappingFieldRef; "observedAtFieldRef": null | MappingFieldRef; "timezonePolicy": MappingTimezonePolicy; "precision": "SECOND" | "MILLISECOND" | "MICROSECOND"; "validFromFieldRef": null | MappingFieldRef; "validToFieldRef": null | MappingFieldRef };

export type MappingTimezonePolicy = { "kind": "UTC" | "REGISTERED_ZONE"; "zoneId": null | string };

export type MappingUnitSpec = { "id": string; "sourceUnitIri": string; "targetUnitIri": string; "sourceUnitFieldRef": MappingFieldRef; "sourceUnitCode": "Cel" | "K"; "unitRegistryVersion": "1"; "evidenceKind": "SOURCE_FIELD" };

export type MappingValidateRequest = { "target": MappingValidationTarget; "command": CommandContext };

export type MappingValidationTarget = MappingValidationTargetMappingPublishTarget | MappingValidationTargetMappingRollbackTarget;

export type MappingValidationTargetMappingPublishTarget = { "kind": "PUBLISH"; "draftRevision": number };

export type MappingValidationTargetMappingRollbackTarget = { "kind": "ROLLBACK"; "targetReleaseId": string; "manifestHash": string };

export type MappingVersionBinding = { "sourceConnectionId": string; "connectionRevision": number; "configHash": string; "sourceType": "POSTGRESQL"; "sourceCatalogSnapshotId": string; "sourceCatalogFingerprint": string; "ontologyReleaseId": string; "ontologyManifestHash": string; "mappingHash": string; "validationHash": string; "impactHash": string; "assessmentId": string; "adapterVersion": "pg-mapping-v1"; "executorVersion": "mapping-validator-v1"; "canonicalVersion": "mapping-c14n-v1"; "secretVersion": number; "authorizationEpoch": number };

export type OracleColumnMetadata = { "dataTypeOwner": null | string; "byteLength": null | number; "charLength": null | number; "charSemantics": "BYTE" | "CHAR" | null; "fractionalSecondsPrecision": null | number; "timeZoneKind": "NONE" | "WITH_TIME_ZONE" | "WITH_LOCAL_TIME_ZONE" | "UNKNOWN"; "supportStatus": "SUPPORTED" | "METADATA_ONLY" | "UNSUPPORTED" };

export type OracleConnectionProfile = { "host": string; "port": number; "serviceName": string; "username": string; "tls": boolean; "allowedOwners": Array<string> };

export type PgConnectionProfile = { "host": string; "port": number; "database": string; "username": string; "sslMode": string; "allowedSchemas": Array<string> };

export type ResourceScope = { "organizationId": string; "siteIds": Array<string> };

export type SecretIntakeReceipt = { "secretRef": string; "expiresAtUtc": string; "usageLimit": number; "credentialVersion": number };

export type TdengineConnectionProfile = { "wsUrl": string; "database": string; "timePrecision": string; "timeZone": null | string };

export type WebApiConnectionProfile = { "baseOrigin": string; "operationId": string; "method": string; "approvedPath": string; "authentication": string; "pagination": string; "hostPolicyRef": string };
