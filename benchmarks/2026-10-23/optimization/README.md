# Optimized Goose: validation and measurement evidence

[PR #32](https://github.com/arjaythedev/multicore-server-challenge/pull/32) is **ready for review** at `23a14e8`. Clean native x86 validation passes all18 stages. **First place is not established.** The [official snapshot](../README.md) still ranks the earlier submission **#8 /65,000 users**. A [fresh check at17:50UTC](publication/official-check-1730/summary.md) confirms the optimized revision remains open, unmerged and unscored; upstream CI awaits maintainer approval. No historical official score is reassigned to this new source.

No implementation completed a qualified300-second hold in these local searches. The table below shows the **one completed60-second matched100,000-user point** for the final PR binary, not a capacity ranking.

| Implementation | Correctness | Target CPU ms/success at100k | p50 / p95 / p99 ms at100k | Errors at100k | Qualified300s users |
|---|---|---:|---:|---:|---:|
| [Goose #32, current optimized source](https://github.com/arjaythedev/multicore-server-challenge/pull/32) | **PASS**, ARM dev/full197 and complete native x86 checks |0.160411 |2.961 /6.603 /46.751 |0 |— |
| [Rust #7, unchanged control](https://github.com/arjaythedev/multicore-server-challenge/pull/7) | **PASS**, full197 on exact benchmark binary |0.191172 |0.812 /15.703 /78.463 |0 |— |

Goose used **16.09% less combined app+PostgreSQL CPU per successful request** at that point. Its median, mean and maximum latency were higher: mean4.459 versus4.148ms; max669.695 versus332.287ms. Both phases were native-qualified with zero measured or timeline errors. Request counts differ by450 (0.0283%); common user/seed inputs do not imply identical complete request traces. The [independent point audit](audit/final-source-100k-comparison.md) reproduces histograms, clocks, counts and resources. This is one exploratory load point, not a stable≥5% or first-place result.

## Current source and validation

Source commit `23a14e8cbf32113509cd0ad941320ef947508981`, submission tree `334be131b9c0297e78a2377656e207a11a0bada6`, is identical to the [green Ubuntu x86 validation](https://github.com/tbsvttr/multicore-server-challenge/actions/runs/39937895836). All18 stages pass: clean pinned compiler/app build; four197-step conformance runs;293,966 native assertions;4,000 Goose JWT assertions;252 bcrypt comparisons;1,664 concurrent-read oracle requests; quiet timers, deferred commit/rollback, favorite/update/rename races and trusted Go NUL-password interoperability. [CI receipts](ci/executed/verified-green-receipt.json) verify source equality, artifact digests, normal UID1001 and NOFILE200000. Earlier CI harness failures remain archived.

The final ARM binary is `7a7c31fb…`; x86 is `acf76363…`. ARM independently passes dev/full197 and the same [read](builds/read_final/result.json), [runtime](builds/runtime_final/result.json), [timer](builds/quiet_final/result.json) and [race/password](builds/safety_new/result.json) checks. [Source transfer](audit/final-source-transfer.json) and [independent review](audit/leader1-independent-review.md) retain provenance. Different architectures/build paths produce different binaries; no bit-identical rebuild claim is made.

Defaults: two event loops, three readers and one writer each (**eight PG connections total**), two bcrypt workers,32-member read batches,5ms eligible read collection and1ms writer collection. SQL shares work only within the current execution and retains viewer flags. JWT validation and cost-10 bcrypt remain real; responses follow commit. Fresh article metadata is read by immutable ID. There is no cross-request result cache, schema/cluster tuning, CPU affinity or worker restart. Submission NOTICE.md/LICENSE retain all origins.

## Conditions and preserved attempts

The app and PostgreSQL18 share **8CPU /16GiB /no swap**, original full seed/schema and durable cluster settings. Every app runs as normal UID with actual descriptor witnesses. This shared ARM64 Mac/Docker setup is not the official dedicated x86 target with a separate physical load host. The native workload binary remains `886eaa56…`; SLO stays p95<500ms, p99<1s, errors<1%. Only a qualified300-second hold could produce a held-user score. Every new study uses fresh full-seed databases and a standard10k warmup; no old phase is reused.

- [First study](audit/capacity-first-result.md): client4CPU/8GiB; Rust80k passed,160k genuinely overloaded the generator. Operator stopped the whole study; Goose warmup was interrupted before measurement.
- [Second study](audit/capacity-v2-result.md): client8CPU/8GiB; both160k probes retained genuine scheduling failures.
- [Gradual study](audit/capacity-v3-result.md):100k start,10% growth,130k ceiling; Rust100k passed, then real Mac sleep invalidated Rust110k and Goose warmup.
- [Powered repeat](audit/capacity-powered-result.md): same protocol after AC/awake confirmation; Rust100k native-qualified and110k locally qualified. Rust120k and Goose110k suffered scheduling failures and end-to-end SLO failures. Goose100k is the completed point above. Invalidity does **not** exonerate the application; higher-load cause remains unresolved.
- [Narrow Rust follow-up](audit/capacity-rust110-115-result.md): fresh110k–115k plan, unchanged control; even110k had generator stalls, so115k/holds were never reached.

All five searches stopped before any hold. Invalid generation never becomes a server failure boundary or zero capacity score. Raw native verdicts, errors, histograms and monitors remain intact.

Native `/proc/stat` includes the entire Docker VM, including the server. V2/V3 preregister separate **local** qualification using the generator cgroup≤75%, while preserving all native flags and every scheduling, active-user, histogram, clock, coverage, OOM and SLO gate. A CPU-only whole-VM flag can differ; genuine stalls cannot. [Diagnosis](audit/client-cpu-diagnosis.md), [v3 rules](capacity-v3/CAPACITY.md) and62/72-test proofs document this accounting distinction. Native-flagged local phases are never presented as official/native-qualified scores.

## Diagnosis and unpromoted work

The fixed [instrumented replay](diagnostics/goose110-gc-pg/README.txt) added GC logs and1Hz PG samples to unchanged binaries. Its warmup had relation-lock blocking, and its100k phase was incomplete after the deadline;110k was not reached. At100k, client CPU rose while most sampled PG backends were idle. No seconds-long STW pause was recorded, and one40-second sampler gap occurred between GC collections. [PG analysis](audit/diagnostic-goose110-pg.md) and [GC analysis](audit/diagnostic-goose110-gc.md) retain partial-data limits. The [runtime review](audit/gc-ffi-diagnostic-review.md) confirms Goose itself has no tracing GC/STW pause. The cause of the original110k collapse remains unresolved.

A separate P2 diagnostic is frozen with GOMAXPROCS2 and enriched blocker observations. Its first invocation stopped at the AC-power check **before any load**. The Mac later reported1% battery and discharging despite intermittent AC. All owned PG/benchmark containers were [stopped cleanly](audit/low-power-resource-cleanup.json); no timing guard was waived. Unrelated containers were untouched, datasets preserved, and a persistent local backup includes the original binaries and continuation state. Further load tests require effective charging and an awake Mac.

`candidates/leader2` is an **unpromoted prototype**, not a second submitted implementation. It adds generation-safe age-ordered read queues, early cancellation of unsent reads, reader Sync groups of4 and a4-group cap; writer groups stay64. With default32-member batches this bounds each reader to16 executions/512 HTTP requests. It passes dev/full197, read1664, commit/rollback/timer/race/NUL probes. Its new wire-observed admission probe is prepared but unexecuted; native x86 and performance validation remain pending. It has not replaced source23a or received a score. [Review](audit/leader2-independent-review.md) and [notes](audit/leader2-hardening-notes.md) retain all earlier prototype versions.

An earlier `a34ee531…`80k calibration selected the current configuration with26.3% less target CPU/success but slower median/p95. It measured a different binary and is not transferred to the final source. [Selection](audit/calibration-selection.json), [audit](audit/calibration-result.md) and all four23October runs under `historical-profiles/` remain. Baseline bug reproductions, runtime-observer timeout, rejected feed-window experiment and diagnostic-plan provenance limitations are preserved. No invalid trial was replaced within its study.

## Export and reproducibility

[Result JSON](result-summary.json), full plans/tools, raw data, reviews and receipts are retained. The manifest records copied and omitted binary/cache paths with hashes. `PREEXPORT-BINARY-AUDIT-RECEIPTS.json` verifies the original frozen binaries against completed capacity audits before omission from this public text bundle. Original paths remain; complete controller replay needs the original build environment/binaries and path setup. [Compiler provenance](audit/compiler-provenance.json) verifies the pinned archive/all4,179 source files without claiming bit-identical ELFs. Earlier official comparisons and raw archives remain unchanged.
