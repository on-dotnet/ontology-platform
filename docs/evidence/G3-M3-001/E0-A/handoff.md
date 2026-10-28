# E0-A canonical Fuseki implementation handoff

Status: DRAFT / PARTIAL. BaseSha `67332cace3d134e31b723226071f1d630453cd59`; branch `codex/g3-m3-efficiency`. Commit Head is supplied by the handoff message. No push, merge, new dependency, registry publication, paid quota or shared CI/AppHost change was performed.

## Implemented interface

`--identity` emits the frozen eight fields: schemaVersion, cacheKey, failureStateKey, envFingerprint, inputFingerprint, contextSha256, platform and image. Engine platform is normalized from docker info; the stable image key fingerprints full context, frozen Jena/base inputs, platform and helper bytes. Failure keys additionally fingerprint exact Engine/Buildx version and Engine platform.

Backward-compatible build accepts `--platform`, `--restore-cache`, `--export-cache`, `--failure-state`, and `--final-gate`. Receipts include cacheOutcome/restored/reused, producerRunId (producerHead for restored images), currentGithubRunId, runner and measured stages. sourceChecksumVerified reports actual cold checksum markers or explicitly preserved producer provenance; a local reused image does not claim a fresh download.

Export requires an empty dedicated directory. Restore and export should use different directories when restore contains data; reusing a nonempty restore directory for export is refused. Cache has exactly image.tar and receipt.json. Validation rejects schema/hash/tag/platform/ownership mismatches, links, special files, traversal, duplicate/unreferenced tar members and inconsistent OCI descriptors before load. Corruption falls back to one canonical build; any load/loaded-identity failure stops without overwriting unknown images. Legacy config IDs and modern OCI root manifest/index IDs are bound to config/layer content. Legacy uncompressed layers are verified against rootfs diff_ids; OCI blobs are hash/size checked and bound to the same Docker manifest/config/platform. Only one runtime platform/manifest is accepted. Canonical builds explicitly use --provenance=false to prevent extra attestation manifests entering the single-runtime cache; older tagged images have different helper-derived keys and are not silently reused.

Failure candidates are strict allowlisted JSON with output hashes/sizes. New invocations validate input/environment, run bounded fixed-origin HEAD probes, and return exit2 only when the terminal stage/category actually reproduces. Changed input/environment invalidates the candidate. --final-gate bypasses candidate stop-loss and performs actual preflight/inspect/build as required. Source COPY preflight, download/checksum/extract and cache stages are separate. Final failed markers take precedence over recovered earlier network errors. Repeated BuildKit error-summary markers are counted once.

## Actual verification

- `python3 scripts/tests/CanonicalFuseki.Tests.py`: PASS, 20 tests (canonical-tests.txt).
- `python3 scripts/tests/FusekiCache.Tests.py`: PASS, 37 tests (cache-tests.txt).
- Red logs preserve observed failures before fixes, including modern OCI ID handling, regular COPY inputs, empty-cache miss, timeout classification, malformed labels, terminal error classification, mixed-origin failures and duplicate stage accounting.
- `git diff --check`: PASS, exit0 at source freeze.
- Complete `verify.ps1 -SelfTest` was started; selftest-cutoff.txt is an explicit in-progress snapshot, NOT_VERIFIED at this handoff cutoff. Master performs the integrated complete run; no incomplete output is claimed PASS.

Real Engine: Linux arm64, Docker 29.9.2, existing shared desktop-linux backend. The actual canonical --final-gate cold/export command failed with exit1 after 306.582 seconds: primary HTTP failure (118221ms), fallback timeout (180016ms). No new canonical image or image cache was produced. The original sanitized receipt is retained unchanged, including its earlier duplicate markers and first-error classification. Final source fixes these findings, but no second expensive cold build was attempted.

A subsequent real bounded HEAD probe observed NETWORK_TIMEOUT in 10140ms. A second real bounded probe using an isolated candidate derived from that actual HEAD observation returned NOT_REPRODUCED in 9843ms; at least one origin recovered. No Docker build was invoked. This is separate from the earlier cold-build candidate, whose input changed when the implementation/context was fixed. We do not claim a real exit2 when the network did not reproduce. Persistent exit2, final-gate actual build and changed-input bypass are exercised by the 37-test suite with external command boundaries controlled.

Existing Engine docker-save format was inspected read-only: OCI index/root ID differs from config ID and historical images include attestations. This observation drove the OCI regression and --provenance=false change. Final-source real export/load, independent GitHub runner cold/export then restore/load, and amd64 runtime execution remain BLOCKED / NOT_RUN locally. CanonicalFuseki.Real.Tests.py now performs actual export, validation, docker load and restored reuse without deleting tags; Master can run it when the required canonical image can be built. Fixture tests are not presented as those real successes.

## Resource ownership and remaining gate

TaskId G3-M3-001 / RunId e0-a-real-cold owns new failed Buildx ref `20b0q7l3v4hjmtem8si9g0lxc`; preserve its sanitized failure before Master reviews exact cleanup. No containers or volumes were created. Ignored artifacts/e0-a-real-failures contains the original failure candidate; artifacts/fuseki-builds contains invocation receipts. No old image/history/volume was deleted. The temporary read-only existing-image export at /private/tmp/e0-a-existing.tar is regenerable and remains for Master exact cleanup; it is not packaged. Temporary probe state was automatically removed after the bounded test. Private runtimes/PFX/credentials were not read or copied.

Master owns CI/cache budget guard, verify registration, AppHost, independent review, actual cross-run proof, push/integration and final V3 ZIP. Stop at E0-A implementation handoff; no READY claim for all E0 or M3.
