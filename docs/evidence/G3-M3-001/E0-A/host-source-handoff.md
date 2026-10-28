# Host-source canonical handoff

Implementation commits: a574bdc64d302ae38a357467b7d567e8a14c220d (host prefetch/named context), then 992aefac3a7d3b6b0b634087fb26135f015df066 (independent-review and actual Mac annotation fixes). All source/tests were committed before actual cold verification; evidence is post-committed. No push/main merge, system proxy/network change, package/version change or artifact upload was performed.

## Current behavior and targeted proof

Only an absent exact canonical image enters source preparation. Local reused images skip failure-network probes/source preparation; restore HIT and --identity do not access Apache. Host download uses only the two frozen Apache release URLs, 180s/connect15 per origin, no retry, a maximum 256MiB and at most three manually checked redirects. Redirects must resolve to one of those exact URLs before another request is issued. All host GET/HEAD commands begin curl -q, so default .curlrc cannot inject location, extra URLs, headers or output options. A real isolated CURL_HOME test proves the default-config marker is read without -q and absent with -q, using --version and no network. Read-only source/cache descriptors use nofollow, type/link/size checks, finite streaming SHA512 and an atomic verified-only cache publication; bad hashes do not trigger fallback. Private named contexts contain only fuseki.tar.gz and are removed after use.

The unique docker build receives --build-context fuseki_source and --network=none. The tracked context remains the same six allowlisted files. Dockerfile COPYs the source, actually repeats the frozen SHA512 check, extracts and removes the temporary archive. Host cache/hash/network operations use existing stage names plus controlled executor=host/operation fields; parsed container checksum/extract markers use executor=container. Warm receipts do not claim a fresh source verification. No helper was split out, so the full helper byte fingerprint continues to cover all source logic.

New failure candidates originate at the host executor. Their bounded HEAD probe uses that executor; the historical container probe remains explicitly testable but is not the new host-download gate. Checksum candidates actually re-open and hash the same source cache: unchanged corruption blocks with exit2, repaired bytes permit continuation and old state stays. The real tests now parse arguments before Docker access: --help exits0 and unknown flags exit2, both proven with a Docker-access marker that remains absent.

Final targeted checks: canonical34 + cache66 + transfer17 = 117 passing tests; range diff-check exit0. Initial RED, intermediate fixture-boundary failures and final green logs remain attached. Intermediate test migration failures were resolved by isolating external preparation in build tests and explicitly retaining the legacy container executor in its own tests; the new actual source hash/download cases exercise production source functions.

## Actual Mac observations

Master's exact approved host tar was copied read-only into the shared hash-named project cache with another actual SHA512 verification: 51398669 bytes, 65ms copy/verification, downloadPerformed=false. This is not a fabricated fresh download time.

The one actual cold attempt ran committed a574 source, built the current-at-that-point canonical image, and exported a 198898176-byte tar. It failed at the strict export validation in 20.173s because OCI_DESCRIPTOR_ANNOTATIONS rejected config.digest. The original failure receipt/trace are unchanged. The [official BuildKit metadata documentation](https://github.com/moby/buildkit/blob/master/README.md#metadata) documents that annotation. The corrective validator allows it only on a manifest descriptor, bound exactly to the hash of actual config bytes; a root/manifest image ID in its place or any unknown annotation still fails. No broad metadata exception was added.

The already-produced archive was then independently reopened with validator 992. Its input identity was recomputed from precise a574 Git objects for the six context files and helper, rather than trusting self-declared receipt fields. Strict validation passed, actual docker load passed, restore HIT and exact old-identity reuse passed, and before/after image IDs/history refs were identical. Six checks passed in 2706ms. ProducerHead remains a574; validatorHead is 992. This validates that existing committed producer artifact and does not claim a cold build under the changed 992 fingerprint. No second cold build or download was made.

Separately, the actual isolated --source-failure-only test passed six checks in 358ms: first process performed one real source hash check and failed CHECKSUM_MISMATCH/exit1 in 150ms; a new process read persisted state, performed another actual hash check and blocked exit2 in 129ms. Both had zero Docker builds and zero downloads. The unique synthetic context/Git/state were removed on exit; Docker was used only for identity and absent-tag inspection. This run used the committed core a574 implementation before the later q/annotation/CLI correction.

## Exact remaining commands and ownership

Master performs the one final-input Mac roundtrip from the integrated clean source tree:

```sh
python3 scripts/tests/CanonicalFuseki.Real.Tests.py
```

The existing shared source cache is already prepared under the original repository artifacts/fuseki-sources with its full frozen SHA512 filename. The script creates a fresh dedicated ignored export directory, performs actual load, and verifies subsequent restore/reuse does not add image IDs/history. The optional isolated short-failure command is:

```sh
python3 scripts/tests/CanonicalFuseki.Real.Tests.py --source-failure-only
```

A final Linux new-key cold/export/save and separate-run restore, integrated full SelfTest/same-Head CI, current-input Mac roundtrip, final resource review and V3 package remain Master-owned. Status remains PARTIAL until those actual gates pass. ARM64 transfer stays BLOCKED_ACCOUNT_BUDGET_UNKNOWN; no budget proof, workflow or upload was activated.

Owned local image from the single worker cold: sha256:8d68acc51924c158b418c8bd5597ca20203d2f0ce35799ceb04c068a8b991a7e, tag/input fingerprint 627fad8936708ae759a8f889ba60fe146e31970a40a823c33b629abc7feec3b7, TaskId G3-M3-001 / RunId e0-a-real-d576598ea1ec4196ac481a4e2425a486-export. Its exact Buildx history ownership is deferred to Master's existing bounded lifecycle inspector. The ignored export lives at artifacts/e0-a-real-d576598ea1ec4196ac481a4e2425a486; no tar is committed or packaged. The source cache is regenerable approved public bytes; retain it for final verification, then classify duplicate host-preflight copies and these exact image/archive resources at stage closeout. No containers/volumes/old images were deleted or privately inspected by this worker.
