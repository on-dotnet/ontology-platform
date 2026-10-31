// 从g2-platform.openapi.json自动生成；运行pnpm generate:types，禁止手工编辑。
// 新只读DTO来自g2-models生成Schema；此补充不代表路由已实测。

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type OwlExpressionDiagnostic = { "code": string; "message": string; "focusNode": RdfTerm | null; "predicateIri": string | null; "line": number | null; "column": number | null };

export type OwlExpressionProperty = { "predicateIri": string; "values": Array<RdfTerm> };

export type OwlExpressionNode = { "term": RdfTerm; "kind": string; "properties": Array<OwlExpressionProperty>; "orderedItems": Array<RdfTerm> };

export type OwlExpressionSource = { "sourceId": string; "sourceHash": string; "status": string; "sourcePreserved": boolean; "readOnlyStructured": boolean; "editable": boolean; "publishEligible": string; "inferred": boolean; "roots": Array<RdfTerm>; "nodes": Array<OwlExpressionNode>; "diagnostics": Array<OwlExpressionDiagnostic> };

export type OwlExpressionSnapshot = { "projectionVersion": string; "version": VersionRef; "scope": ResourceScope; "hashes": SourceHashes; "profileId": string; "profileVersion": string; "profileHash": string; "sources": Array<OwlExpressionSource> };

export type ActivateReleaseRequest = { "proposalId": string; "expectedActivationRevision": number; "expectedActiveReleaseId": string | null; "command": CommandContext };

export type ActorContext = { "subjectId": string; "organizationId": string; "siteIds": Array<string>; "roles": Array<string>; "traceId": string; "correlationId": string };

export type ApprovalDecision = "approve" | "reject";

export type ApprovalDecisionRequest = { "decision": ApprovalDecision; "command": CommandContext };

export type ApprovalRecord = { "approvedBy": string; "decision": ApprovalDecision; "decidedAtUtc": string; "bindingHash": string };

export type ApprovalRequiredPayload = { "kind": "approval.required"; "approvalId": string; "proposalId": string; "operation": ProposalKind; "scope": ResourceScope; "expiresAtUtc": string };

export type ArtifactObject = { "objectKey": string; "hash": string; "sizeBytes": number; "contentType": string };

export type AssessmentDiagnostic = { "sourceId": string; "sourceHash": string; "diagnostic": SemanticDiagnostic; "line": number | null; "column": number | null; "sourceShape"?: RdfTerm | null };

export type AssessmentStage = { "name": string; "status": AssessmentStageStatus; "code": string };

export type AssessmentStageStatus = "PASS" | "FAIL" | "NOT_RUN" | "NOT_SUPPORTED" | "INDETERMINATE";

export type AssetVersion = { "assetId": string; "version": string };

export type AssetVersionSnapshot = { "releaseId": string; "ontologyHash": string; "shapesHash": string; "vocabularyHash": string | null; "dataHash": string; "ontologyGraphIri": string; "dataGraphIri": string; "mappingVersions": Array<AssetVersion>; "metricVersions": Array<AssetVersion>; "ruleVersions": Array<AssetVersion>; "capabilityVersions": Array<AssetVersion> };

export type AuditCommand = { "action": string; "resource": string; "outcome": string; "scope": ResourceScope };

export type CancelRunRequest = { "command": CommandContext };

export type CapabilityBudget = { "maxDepth": number; "maxRows": number; "timeoutMs": number; "maxToolCalls": number };

export type CapabilityInputSchema = { "schemaVersion": number; "type": string; "required": Array<string>; "properties": Array<CapabilityParameter>; "additionalProperties": boolean };

export type CapabilityParameter = { "name": string; "type": string; "description": string; "enumValues": Array<string>; "minimum": number | null; "maximum": number | null; "itemsType": string | null };

export type CommandContext = { "commandId": string; "idempotencyKey": string; "expectedRevision": number; "reason": string };

export type CompareVersionsRequest = { "from": VersionRef; "to": VersionRef };

export type CreateDraftRequest = { "name": string; "scope": ResourceScope; "sources": SourceBundle; "baseReleaseId": string | null; "command": CommandContext };

export type CreateProposalRequest = { "kind": ProposalKind; "draftId": string | null; "draftRevision": number | null; "hashes": SourceHashes | null; "validationReportId": string | null; "targetReleaseId": string | null; "targetManifestHash": string | null; "command": CommandContext; "impactReportId"?: string | null; "impactHash"?: string | null };

export type CreateRunRequest = { "prompt": string; "plan": SemanticQueryPlan; "providerMode": ProviderMode; "command": CommandContext };

export type CsrfResponse = { "requestToken": string } & Record<string, JsonValue>;

export type DiagnosticSeverity = "info" | "warning" | "error";

export type DraftDiff = { "baseRevision": number; "targetRevision": number; "baseHashes": SourceHashes; "targetHashes": SourceHashes; "addedTriples": Array<RdfTriple>; "removedTriples": Array<RdfTriple>; "sourceDiff": string; "unsupportedDiagnostics": Array<SemanticDiagnostic> };

export type DraftPublicationSnapshot = { "draft": OntologyDraft; "validation": SemanticValidationReport; "semantics"?: PublicationSemantics | null };

export type EditDraftRequest = { "edit": SemanticEdit; "command": CommandContext };

export type EntityCandidate = { "entityIri": string; "entityTypeIris": Array<string>; "externalId": string; "organizationId": string; "siteId": string; "label": string; "evidenceIds": Array<string> };

export type EvidenceAddedPayload = { "kind": "evidence.added"; "evidence": EvidenceRef };

export type EvidenceRef = { "evidenceId": string; "releaseId": string; "scope": ResourceScope; "graphIri": string; "subjectIri": string; "predicateIri": string; "objectTerm": RdfTerm; "sourceId": string; "sourceRecordId": string; "sourceObjectKey": string; "contentHash": string; "validFromUtc": string; "validToUtc": string | null; "observedAtUtc": string; "modelVersion": string; "mappingVersion": string | null; "synthetic": boolean };

export type ExecutionEvent = { "runId": string; "seq": number; "eventId": string; "eventType": "run.started"; "schemaVersion": 1; "occurredAtUtc": string; "snapshot": AssetVersionSnapshot; "payload": RunStartedPayload } | { "runId": string; "seq": number; "eventId": string; "eventType": "tool.started"; "schemaVersion": 1; "occurredAtUtc": string; "snapshot": AssetVersionSnapshot; "payload": ToolStartedPayload } | { "runId": string; "seq": number; "eventId": string; "eventType": "tool.completed"; "schemaVersion": 1; "occurredAtUtc": string; "snapshot": AssetVersionSnapshot; "payload": ToolCompletedPayload } | { "runId": string; "seq": number; "eventId": string; "eventType": "evidence.added"; "schemaVersion": 1; "occurredAtUtc": string; "snapshot": AssetVersionSnapshot; "payload": EvidenceAddedPayload } | { "runId": string; "seq": number; "eventId": string; "eventType": "message.delta"; "schemaVersion": 1; "occurredAtUtc": string; "snapshot": AssetVersionSnapshot; "payload": MessageDeltaPayload } | { "runId": string; "seq": number; "eventId": string; "eventType": "approval.required"; "schemaVersion": 1; "occurredAtUtc": string; "snapshot": AssetVersionSnapshot; "payload": ApprovalRequiredPayload } | { "runId": string; "seq": number; "eventId": string; "eventType": "run.completed"; "schemaVersion": 1; "occurredAtUtc": string; "snapshot": AssetVersionSnapshot; "payload": RunCompletedPayload } | { "runId": string; "seq": number; "eventId": string; "eventType": "run.failed"; "schemaVersion": 1; "occurredAtUtc": string; "snapshot": AssetVersionSnapshot; "payload": RunFailedPayload } | { "runId": string; "seq": number; "eventId": string; "eventType": "run.cancelled"; "schemaVersion": 1; "occurredAtUtc": string; "snapshot": AssetVersionSnapshot; "payload": RunCancelledPayload };

export type ExecutionPayload = RunStartedPayload | ToolStartedPayload | ToolCompletedPayload | EvidenceAddedPayload | MessageDeltaPayload | ApprovalRequiredPayload | RunCompletedPayload | RunFailedPayload | RunCancelledPayload;

export type ExecutionPayloadApprovalRequiredPayload = { "kind"?: "approval.required"; "approvalId": string; "proposalId": string; "operation": ProposalKind; "scope": ResourceScope; "expiresAtUtc": string };

export type ExecutionPayloadEvidenceAddedPayload = { "kind"?: "evidence.added"; "evidence": EvidenceRef };

export type ExecutionPayloadMessageDeltaPayload = { "kind"?: "message.delta"; "text": string };

export type ExecutionPayloadRunCancelledPayload = { "kind"?: "run.cancelled"; "status": ExecutionStatus; "code": string; "totalToolCalls": number | string };

export type ExecutionPayloadRunCompletedPayload = { "kind"?: "run.completed"; "status": ExecutionStatus; "totalToolCalls": number | string; "lastResultStatus": null | SemanticQueryStatus };

export type ExecutionPayloadRunFailedPayload = { "kind"?: "run.failed"; "status": ExecutionStatus; "code": string; "totalToolCalls": number | string };

export type ExecutionPayloadRunStartedPayload = { "kind"?: "run.started"; "providerMode": ProviderMode; "capabilityIds": Array<string>; "maxToolCalls": number | string; "timeoutMs": number | string };

export type ExecutionPayloadToolCompletedPayload = { "kind"?: "tool.completed"; "invocationId": string; "result": SemanticQueryResult; "durationMs": number | string };

export type ExecutionPayloadToolStartedPayload = { "kind"?: "tool.started"; "invocationId": string; "capabilityId": string; "capabilityVersion": string; "plan": SemanticQueryPlan };

export type ExecutionRun = { "runId": string; "ownerSubjectId": string; "scope": ResourceScope; "snapshot": AssetVersionSnapshot; "status": ExecutionStatus; "providerMode": ProviderMode; "createdAtUtc": string; "updatedAtUtc": string; "lastSeq": number; "cancelRequested": boolean; "leaseOwner": string | null; "leaseUntil": string | null; "fencingToken": number; "traceId": string };

export type ExecutionStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export type GenerateImpactReportRequest = { "from": VersionRef; "to": VersionRef; "baselineKind": ImpactBaselineKind; "assessmentId": string | null; "command": CommandContext };

export type GraphComparisonBudget = { "maxBlankNodes": number; "maxSearchNodes": number; "timeoutMilliseconds": number };

export type GraphComparisonResult = { "status": GraphComparisonStatus; "code": string; "visitedNodes": number; "elapsedMilliseconds": number };

export type GraphComparisonStatus = "EQUIVALENT" | "DIFFERENT" | "INDETERMINATE";

export type IdentityTimeEditsRequest = { "hashes": SourceHashes; "changes": Array<VocabularyChange>; "command": CommandContext };

export type ImpactApprovalBinding = { "reportId": string; "canonicalHash": string; "inputFingerprint": string; "baselineKind": ImpactBaselineKind; "from": VersionRef; "to": VersionRef; "baseHashes": SourceHashes; "targetHashes": SourceHashes; "baseManifestHash": string | null; "targetSemantics": PublicationSemantics; "generatedAtUtc": string; "expiresAtUtc": string };

export type ImpactBaselineKind = "VERSION_PAIR" | "INITIAL";

export type ImpactConclusion = { "code": string; "message": string; "blocking": boolean; "affectedIris": Array<string>; "assetReferences": Array<string>; "evidence": Array<ImpactEvidenceReference> };

export type ImpactEvidenceReference = { "version": VersionRef; "sourceId": string; "sourceHash": string; "triple": RdfTriple | null; "focusIri": string | null; "path": string | null; "line": number | null; "column": number | null };

export type ImpactReport = { "schemaVersion": number; "reportId": string; "inputFingerprint": string; "canonicalHash": string; "executorVersion": string; "budgetIdentity": string; "generatedAtUtc": string; "expiresAtUtc": string; "baselineKind": ImpactBaselineKind; "diff": VersionDiff; "profileVersion": string; "profileHash": string; "targetSemantics": PublicationSemantics | null; "changedIris": Array<string>; "assetReferences": Array<string>; "knownImpacts": Array<ImpactConclusion>; "blockers": Array<ImpactConclusion>; "unknownCoverage": Array<ImpactConclusion>; "publishEligible": boolean };

export type ImportLock = { "ontologyIri": string; "hash": string; "objectKey": string };

export type JsonElement = JsonValue;

export type MessageDeltaPayload = { "kind": "message.delta"; "text": string };

export type OntologyDescription = { "classIris": Array<string>; "objectPropertyIris": Array<string>; "datatypePropertyIris": Array<string>; "labels": Array<SemanticPropertyValue>; "supportedAxioms": Array<string>; "diagnostics": Array<SemanticDiagnostic> };

export type OntologyDraft = { "draftId": string; "assetId": string; "scope": ResourceScope; "baseReleaseId": string | null; "revision": number; "etag": string; "name": string; "sources": SourceBundle; "hashes": SourceHashes; "ownerSubjectId": string; "updatedAtUtc": string; "projection": SemanticProjection };

export type PlatformAuditEntry = { "id": string; "occurredAtUtc": string; "actor": string; "action": string; "resource": string; "outcome": string; "traceId": string; "correlationId": string; "organizationId": null | string; "scopeSiteIds": null | Array<string>; "siteId": null | string } & Record<string, JsonValue>;

export type PlatformIdentity = { "subjectId": string; "displayName": string; "roles": Array<string>; "scopes": Array<PlatformScope> } & Record<string, JsonValue>;

export type PlatformProblem = { "type": string; "title": string; "status": number; "code": string; "traceId": string; "correlationId": string; "detail"?: string; "instance"?: null | string } & Record<string, JsonValue>;

export type PlatformResource = { "id": string; "name": string; "organizationId": string; "siteId": string; "status": string } & Record<string, JsonValue>;

export type PlatformResourceList = { "items": Array<PlatformResource>; "auditId": string; "traceId": string } & Record<string, JsonValue>;

export type PlatformScope = { "organizationId": string; "siteId": string } & Record<string, JsonValue>;

export type ProblemDetails = { "type"?: null | string; "title"?: null | string; "status"?: null | number | string; "detail"?: null | string; "instance"?: null | string } & Record<string, JsonValue>;

export type ProposalKind = "PUBLISH" | "ROLLBACK";

export type ProposalStatus = "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "INVALIDATED";

export type ProviderMode = "disabled" | "deterministic" | "approved_model";

export type PublicationSemantics = { "profileVersion": string; "profileHash": string; "assessmentId": string; "assessmentHash": string };

export type PublishedRdfData = { "ontologyTriples": Array<RdfTriple>; "dataTriples": Array<RdfTriple> };

export type RdfTerm = { "kind": RdfTermKind; "value": string; "datatype": string | null; "language": string | null };

export type RdfTermKind = "iri" | "blank" | "literal";

export type RdfTriple = { "subject": RdfTerm; "predicate": string; "object": RdfTerm };

export type ReleaseActivation = { "activationId": string; "activationRevision": number; "releaseId": string; "previousReleaseId": string | null; "manifestHash": string; "manifest": ReleaseManifest; "auditId": string; "outboxEventId": string; "activatedAtUtc": string; "traceId": string };

export type ReleaseManifest = { "schemaVersion": 1; "releaseId": string; "assetId": string; "scope": ResourceScope; "draftId": string; "revision": number; "hashes": SourceHashes; "ontologyGraphIri": string; "dataGraphIri": string; "importLocks": Array<ImportLock>; "snapshot": AssetVersionSnapshot; "artifactObjects": Array<ArtifactObject>; "createdAtUtc": string; "semantics"?: null } | { "schemaVersion": 2; "releaseId": string; "assetId": string; "scope": ResourceScope; "draftId": string; "revision": number; "hashes": { "ontologyHash": string; "shapesHash": string; "vocabularyHash": string | null; "dataHash": string; "bundleHash": string }; "ontologyGraphIri": string; "dataGraphIri": string; "importLocks": Array<ImportLock>; "snapshot": AssetVersionSnapshot; "artifactObjects": Array<ArtifactObject>; "createdAtUtc": string; "semantics": PublicationSemantics };

export type ReleaseProposal = { "proposalId": string; "kind": ProposalKind; "assetId": string; "scope": ResourceScope; "draftId": string | null; "draftRevision": number | null; "hashes": SourceHashes | null; "validationReportId": string | null; "targetReleaseId": string | null; "targetManifestHash": string | null; "submittedBy": string; "submittedAtUtc": string; "expiresAtUtc": string; "status": ProposalStatus; "revision": number; "approval": ApprovalRecord | null; "semantics"?: PublicationSemantics | null; "impact"?: ImpactApprovalBinding | null };

export type ReleaseStatus = "PREPARING" | "ARTIFACTS_VERIFIED" | "GRAPH_DEPLOYED" | "GRAPH_VERIFIED" | "ACTIVE" | "SUPERSEDED" | "FAILED_RETRYABLE" | "FAILED_FINAL";

export type ReleaseSummary = { "manifest": ReleaseManifest; "manifestHash": string; "isActive": boolean; "activationRevision": number; "status": ReleaseStatus; "traceId": string; "impact"?: ImpactApprovalBinding | null };

export type ResourceScope = { "organizationId": string; "siteIds": Array<string> };

export type RunCancelledPayload = { "kind": "run.cancelled"; "status": "CANCELLED"; "code": "cancelled"; "totalToolCalls": number };

export type RunCompletedPayload = { "kind": "run.completed"; "status": "COMPLETED"; "totalToolCalls": number; "lastResultStatus": SemanticQueryStatus | null };

export type RunFailedPayload = { "kind": "run.failed"; "status": "FAILED"; "code": string; "totalToolCalls": number };

export type RunStartedPayload = { "kind": "run.started"; "providerMode": ProviderMode; "capabilityIds": Array<string>; "maxToolCalls": number; "timeoutMs": number };

export type SaveDraftRequest = { "name": string; "sources": SourceBundle; "command": CommandContext };

export type SemanticAnalysis = { "hashes": SourceHashes; "projection": SemanticProjection };

export type SemanticAssessment = { "assessmentId": string; "validationReportId": string; "draftId": string; "revision": number; "hashes": SourceHashes; "profileVersion": string; "profileHash": string; "assessmentHash": string; "assessedAtUtc": string; "expiresAtUtc": string; "executorVersion": string; "stages": Array<AssessmentStage>; "publishEligible": boolean; "diagnostics": Array<AssessmentDiagnostic>; "budgetStatus": string };

export type SemanticCapability = { "id": string; "version": string; "inputSchema": CapabilityInputSchema; "outputSchema": JsonValue; "meaning": string; "policy": string; "executorId": string; "budgets": CapabilityBudget };

export type SemanticCapabilitySupport = { "id": string; "name": string; "edit": string; "preserve": string; "publish": string; "validation": string; "reason": string };

export type SemanticDatum = { "kind": "ontology"; "ontology": OntologyDescription; "entity": null; "relationship": null } | { "kind": "entity"; "ontology": null; "entity": SemanticEntity; "relationship": null } | { "kind": "relationship"; "ontology": null; "entity": null; "relationship": SemanticRelationship };

export type SemanticDatumKind = "ontology" | "entity" | "relationship";

export type SemanticDiagnostic = { "code": string; "severity": DiagnosticSeverity; "message": string; "focusNode": RdfTerm | null; "path": string | null };

export type SemanticEdge = { "id": string; "source": string; "predicateIri": string; "target": string; "label": string };

export type SemanticEdit = { "subjectIri": string; "predicateIri": string; "oldObject": RdfTerm | null; "newObject": RdfTerm | null };

export type SemanticEntity = { "iri": string; "typeIris": Array<string>; "label": string; "externalId": string; "organizationId": string; "siteId": string; "synthetic": boolean; "properties": Array<SemanticPropertyValue> };

export type SemanticNode = { "id": string; "kind": SemanticNodeKind; "label": string; "typeIris": Array<string> };

export type SemanticNodeKind = "class" | "objectProperty" | "datatypeProperty" | "individual";

export type SemanticProjection = { "revision": number; "hashes": SourceHashes; "triples": Array<RdfTriple>; "nodes": Array<SemanticNode>; "edges": Array<SemanticEdge>; "structuralEditAllowed": boolean; "diagnostics": Array<SemanticDiagnostic> };

export type SemanticPropertyValue = { "predicateIri": string; "value": RdfTerm; "evidenceIds": Array<string> };

export type SemanticQueryPlan = { "capabilityId": string; "capabilityVersion": string; "assetId": string; "releaseId": string | null; "entityType": string | null; "entityIri": string | null; "externalId": string | null; "siteId": string | null; "relationshipIris": Array<string>; "depth": number; "maxRows": number; "timeoutMs": number };

export type SemanticQueryResult = { "status": SemanticQueryStatus; "data": Array<SemanticDatum>; "candidates": Array<EntityCandidate>; "evidence": Array<EvidenceRef>; "snapshot": AssetVersionSnapshot; "subSources": Array<SemanticSubSource>; "validTime": TemporalExtent | null; "observedAtUtc": string; "traceId": string; "limited": boolean; "diagnostics": Array<SemanticDiagnostic> };

export type SemanticQueryStatus = "FOUND" | "EMPTY" | "PARTIAL" | "UNAVAILABLE" | "UNAUTHORIZED" | "AMBIGUOUS";

export type SemanticRelationship = { "sourceIri": string; "predicateIri": string; "targetIri": string; "evidenceIds": Array<string> };

export type SemanticSubSource = { "sourceId": string; "status": SubSourceStatus; "releaseId": string; "dataHash": string; "observedAtUtc": string; "code": string | null };

export type SemanticSupportProfile = { "profileId": string; "version": string; "hash": string; "reasoningMode": string; "capabilities": Array<SemanticCapabilitySupport>; "comparisonBudget": GraphComparisonBudget };

export type SemanticValidationReport = { "reportId": string; "draftId": string; "revision": number; "hashes": SourceHashes; "kind": ValidationKind; "conforms": boolean; "issues": Array<ValidationIssue>; "rawReportHash": string; "validatedAtUtc": string; "traceId": string };

export type SourceBundle = { "ontologyTurtle": string; "shapesTurtle": string; "vocabularyTurtle": string | null; "dataTurtle": string };

export type SourceComparison = { "sourceId": string; "leftHash": string | null; "rightHash": string | null; "sourceChanged": boolean; "graph": GraphComparisonResult };

export type SourceHashes = { "ontologyHash": string; "shapesHash": string; "vocabularyHash": string | null; "dataHash": string; "bundleHash": string };

export type SourceVersionDiff = { "sourceId": string; "baseText": string | null; "targetText": string | null; "baseHash": string | null; "targetHash": string | null; "sourceChanged": boolean; "graph": GraphComparisonResult; "baseTripleCount": number | null; "targetTripleCount": number | null; "addedTriples": Array<RdfTriple>; "removedTriples": Array<RdfTriple>; "tripleDeltaStatus": TripleDeltaStatus };

export type SubSourceStatus = "AVAILABLE" | "EMPTY" | "PARTIAL" | "UNAVAILABLE" | "UNAUTHORIZED";

export type TemporalExtent = { "fromUtc": string; "toUtc": string | null };

export type TemporalRelation = "OVERLAP" | "DISJOINT" | "INDETERMINATE" | "INVALID";

export type ToolCompletedPayload = { "kind": "tool.completed"; "invocationId": string; "result": SemanticQueryResult; "durationMs": number };

export type ToolStartedPayload = { "kind": "tool.started"; "invocationId": string; "capabilityId": string; "capabilityVersion": string; "plan": SemanticQueryPlan };

export type TripleDeltaStatus = "EXACT" | "EQUIVALENT" | "INDETERMINATE";

export type ValidateDraftRequest = { "revision": number; "hashes": SourceHashes; "command": CommandContext };

export type ValidationIssue = { "severity": DiagnosticSeverity; "focusNode": RdfTerm | null; "path": string | null; "value": RdfTerm | null; "sourceShape": RdfTerm | null; "constraintComponent": string | null; "message": string; "sourceId": string };

export type ValidationKind = "RDF_PARSE" | "SHACL_CORE" | "OWL_SUPPORT";

export type VersionDiff = { "assetId": string; "scope": ResourceScope; "from": VersionRef; "to": VersionRef; "baseHashes": SourceHashes; "targetHashes": SourceHashes; "baseManifestHash": string | null; "targetManifestHash": string | null; "sources": Array<SourceVersionDiff> };

export type VersionRef = { "kind": VersionRefKind; "id": string; "revision": number | null };

export type VersionRefKind = "DRAFT" | "RELEASE";

export type VocabularyChange = { "sourceId": VocabularyEditSource; "edit": SemanticEdit };

export type VocabularyEditSource = "ontology" | "vocabulary";

export type VocabularyEditsRequest = { "hashes": SourceHashes; "changes": Array<VocabularyChange>; "command": CommandContext };

export type VocabularySnapshot = { "draftId": string | null; "releaseId": string | null; "manifestHash": string | null; "revision": number; "hashes": SourceHashes; "profileVersion": string | null; "profileHash": string | null; "triples": Array<VocabularySourceTriple>; "diagnostics": Array<AssessmentDiagnostic> };

export type VocabularySourceTriple = { "sourceId": string; "triple": RdfTriple };
