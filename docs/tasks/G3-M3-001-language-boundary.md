# G3-M3-001 SEM language-boundary correction

Approved scope: existing M3 terminology language correctness, no dependencies. Base c2cffa6d5b32453ee1603c858d12b7c4102a8702. Master remains only main/CI/contracts writer.

Independent writer uses existing managed g3-m3-sem Worktree, codex/g3-m3-sem-language. Owned paths: VocabularyGovernance.cs under Modules.Ontology, backend/tests/OntologyPlatform.SemanticTests/G3M3GovernanceTests.cs, G3M3VocabularyTests.cs, G3M3ServiceTests.cs, G3M3PublicationPolicyTests.cs, docs/evidence/G3-M3-001/SEM/language-boundary/**. Read-only contracts, Host, fixture/container orchestration, shared build/locks/CI/migrations/all other code.

First prove duplicate BCP47 variant/extension issue through actual Jena RIOT plus M3 evaluation; preserve RED. If reproduced, narrowly reject duplicates, include valid compound tag and casing positive/negative rows, keep existing primary-language unknown behavior, source provenance and Chinese C# XML/local-variable docs. No universal language registry/dependency expansion. Targeted real semantic tests and independent reviewer before Master integration; full CI then formal M3.
