# M3 language subtag uniqueness correction

Base c2cffa6d5b32453ee1603c858d12b7c4102a8702, independent SEM Worktree codex/g3-m3-sem-language. This is a narrow correctness correction within the approved terminology contract.

Real RIOT+PG RED: 4 tests, 3 failures, 1 pass, zero skipped, exit2. RIOT retained duplicate variant `en-1901-1901` and duplicate extension `en-u-ca-gregory-u-nu-latn`; vocabulary governance omitted invalid diagnostics and the production assessment returned GOVERNANCE=Pass for the duplicate extension. The legal `en-a-bbb-x-a-ccc` control passed.

The existing ABNF regex now captures variant and extension singleton groups separately and requires case-insensitive uniqueness for each group. Private-use tails and existing grandfathered alternatives do not enter those captures. This follows RFC5646 sections [2.2.5](https://www.rfc-editor.org/rfc/rfc5646.html#section-2.2.5) and [2.2.6](https://www.rfc-editor.org/rfc/rfc5646.html#section-2.2.6). No registry download or new dependency is introduced.

The same 4 actual PG/Jena tests then passed, zero skipped, exit0. Invalid tags produce the existing `skos_label_language_invalid` Error with exact vocabulary hash/focus/predicate; production assessment has GOVERNANCE=Fail and PublishEligible=false. The private-use control still passes. Both real runs independently removed their two exact owned containers with fixed Engine/labels and before-command-exit-after/no-such-container receipts; validation graph triple count was zero.

Reproduce only the targeted test: set PLATFORM_TASK_ID=G3-M3-001, PLATFORM_EVIDENCE_DIR to this directory, G2_TEST_JENA_IMAGE=ontology-platform-fuseki:context-4fbf23514516632dcb651b5c05bf04e9992da52491607b6cf58de1f7348ff9ab, then run `python3 scripts/acceptance/semantic-roundtrip.py --postgres --filter 'FullyQualifiedName~LanguageTag' --label language-green`. The image was reused; no canonical build or image publication occurred.

Three-file `dotnet format ... --verify-no-changes --include ...` exited0; its workspace warning is recorded in format.txt. Full SelfTest/full semantic suite/formal stack are delegated to Master integrated gates per the requested critical-path convergence. These targeted results do not certify complete M3.
