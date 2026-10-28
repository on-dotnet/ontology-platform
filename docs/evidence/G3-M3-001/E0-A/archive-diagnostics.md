# E0-A archive refusal diagnostics

Follow-up base: 28df96b9c737d32dfa177e92a880777c5afc085c. Status PARTIAL; no archive acceptance condition was loosened.

Linux Run 40693870276 / job 122835360570 had exact cache miss and completed its canonical build before archive export validation refused after 11.594s. The available sanitized receipt did not identify the rejecting condition. LayerSources, tar links and OCI shape differences remain hypotheses; neither is asserted as the root cause without the actual shape. No new cold build was run locally.

validate_archive now emits only fixed validationCheck labels and archiveShape counts/known optional-field indicators. It never emits unknown field names, values, member paths or bytes. Links remain refused. Export validation now reports stage=cache export; restores retain cache restore. This enables the next real Linux run to identify the strict condition that rejected the archive.

RED: three new diagnostics/stage tests failed before the implementation. GREEN: 40 cache tests plus 20 canonical tests passed; working diff-check exit0. These tests verify diagnostic behavior and rejection safety, not that the previously failing CI archive is now accepted. Full integrated SelfTest and actual CI remain Master-owned.
