# Prepared PR31 reference versus W2/ARTICLE1 configuration comparison

This separate plan is prepared and **has not been executed**. Earlier PR31 plans remain untouched. It compares two complete configurations; it cannot isolate the contribution of worker count, article batching, or native primitives.

The separate W2/ARTICLE1 Rust study has now finished with **NOT_ACCEPTED**: its final candidate attempt was clock-invalid, so it did not obtain all three required valid pairs. Defaults remain unchanged. This prepared PR31 comparison remains unexecuted and supplies no performance result.

| Setting | Portable/corrected PR31 reference | Native Goose candidate |
|---|---|---|
| Source | PR31 `43e0919ae5b693c1d3c1e8828b74bb774ef92ee0`, disclosed local derivative | Same frozen source and binary as the W2/ARTICLE1 Rust study |
| `WORKERS` | 4 | 2 |
| `PG_READERS` | 3 | 3 |
| PostgreSQL connections | 12 readers + 4 writers | 6 readers + 2 writers |
| `HASHERS` | 2 | 2 |
| `ARTICLE_BATCH` | Not implemented | 1 |
| JSON/HMAC | Original pure Goose | Native SIMD JSON / prepared OpenSSL HMAC |
| Binary SHA-256 | `5679b2f84562b352aa80faa6491ee9a6496224333881d2d96e585d468a6b67e2` | `6ab318a0ab9389dc2e77ec6122ff077a93adbcc183c6285c347104e0f734b6c3` |

Both retain `BCRYPT_BATCH_MS=250`, `READ_BATCH=32`, and `READ_HOLD=1`. No source, app defaults, compiler, or database setting is changed by this proposal. Both host binaries and every source file listed in their earlier frozen manifests were checked against those witnesses during preparation.

The reference is a local portable/correctness-corrected derivative of PR31, rather than its original x86 binary or official score. It contains the disclosed Goose slice/native syscall and ARM epoll adapter, reliable bcrypt pipe delivery, PostgreSQL connection guard, and committed-favorite response correction. Its JSON, HMAC and JWT call sites remain original pure Goose; it contains no candidate article batching or native JSON/HMAC. The compiler commit and optimization flags match the candidate. Exact source hashes, credits and necessary-change reasons remain in `../pr31-reference/manifest.json` and `../pr31-reference/changes.patch`.

The reference previously passed all 197 unchanged dev and full conformance steps. The exact candidate binary passed all 197 unchanged full-seed steps with W2/ARTICLE1 before its Rust study. Receipts are copied here without changing the originals.

## Frozen protocol and acceptance

The protocol JSON object exactly matches the prior PR31 v3 plan and W2/ARTICLE1 Rust plan: 80,000 users, four synchronized 20k shards, full fresh seed per attempt, think scale 1, 60-second ramp + 60-second measurement + 15-second tail, three pairs AB/BA/AB, target app plus PostgreSQL 8 CPU / 16 GiB with zero swap, no CPU affinity, 4-CPU external load cgroup, and actual normal-UID/200k descriptor checks.

This is a local ARM64 Mac/Docker fixed-load diagnostic. It does not use the official warmup/search/five-minute scoring protocol and cannot prove official capacity, rank, or superiority to all submissions.

Before claiming a local improvement against this disclosed PR31 derivative, every pair must independently pass:

- All six prescheduled attempts eligible, with zero measured and recorded timeline errors, valid infrastructure/monitor witnesses, no generator-limited verdict, and all 80k VUs active.
- At least 5% lower combined application plus PostgreSQL CPU seconds per successful request than PR31. The preregistered primary metric uses the same sampled inner interval as the existing v3 controller; full-window interpolation may only be reported separately.
- Candidate p95 no higher than paired PR31 p95, and candidate p99 no higher than paired PR31 p99.

Retain invalid or failing attempts and let them block acceptance; never replace them selectively or average away a losing pair. Similar closed-model request rates do not measure capacity. Because multiple configuration and implementation differences are present, a passing result applies to these complete frozen configurations only.

Acceptance against Rust required the separate W2/ARTICLE1 Rust study to pass all three preregistered pair criteria. The completed independent audit returned **NOT_ACCEPTED**. This PR31 plan cannot establish or substitute for that Rust result, and it does not automatically promote defaults.

## Execution prerequisites and files

This proposal was not executed. Preparing these files did not launch a benchmark process. The existing v3 controller can later consume `plan.json` in explicit execution mode.

The original independent auditor deliberately requires equal worker counts for its earlier implementation comparison and remains unchanged. A separate auditor revision was prepared to narrowly recognize this plan's declared whole-configuration W4-to-W2 difference while continuing to enforce equal `PG_READERS=3`, `HASHERS=2`, common load, and resource limits. It does not supply a measurement or acceptance result for this unexecuted plan.

- `configuration.json`, `plan.json`, `plan.sha256`: exact cases and frozen native protocol.
- `acceptance.json`: predeclared all-pairs cleanliness, CPU, and latency contract.
- `basis.json`, `preparation-checks.json`: source identity, disclosure, preparation status, and untouched prior-plan hashes.
- `reference-build-validation.json`, `candidate-preflight.json`: existing conformance receipts.
- `*-source-binary-freeze.json`: earlier source/binary witnesses. Their embedded earlier case settings are historical; this new plan alone declares the proposed process environments. Execution must freshly freeze the exact new cases.
- `frozen-tools/`, `frozen-tool-sha256.json`, `host-tool-sha256.txt`: unchanged v3 controller/helpers. Before execution, verify that host copies still match because the controller copies helpers from the evidence root.
