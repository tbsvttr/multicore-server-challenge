# Completed diagnostic: GC and PostgreSQL observations

The diagnostic stopped at 100k after the native phase deadline; four of five shard JSON results are missing. The 110k phase was never reached. This is partial instrumented diagnosis, with no capacity or performance comparison.

Even the 10k warmup had invalid generator timing and failed latency SLOs. It contained a concrete server-side stall: at native t=110.858, all eight app PostgreSQL backends waited on a relation lock behind external PID1456. Sampled query ages were 0.30–0.50s. The blocker role/query was not captured, so calling it autovacuum would be speculation. WALSync/WALWrite waits were also present; the longest active writer sample was about 1.68s. The collector had two failed samples out of188.

The later 100k failure has a different sampled pattern. During t=60–90 and90–120, the client consumed about5.85 and6.15 cores, while target use fell to2.91 and2.29 cores. Most sampled app backend observations were idle/ClientRead, with maximum active query ages of about0.20–0.22s and no sampled blockers in those windows. That supports client/host scheduling or processing starvation; it does not show a sustained PG query/lock stall. Front-end delays, short server stalls and unsampled effects remain possible. The collector had four failed samples out of168, retained explicitly as gaps.

No database deadlock, rollback or temporary-file counter increments were recorded in either phase. Observer read transactions are included in per-DB transaction totals. Checkpointer and WAL activity are recorded, but read/write timing counters of zero do not establish zero I/O wait when timing collection is disabled.

The independent [GC report](diagnostic-goose110-gc.md) parsed all91 GC lines. No recorded stop-the-world pause exceeds91ms. Concurrent marking reaches11.193s, which is not a stop-the-world pause. Shard1 has a40.17s actual sampler gap entirely between recorded collection phases, even with the full timing-origin uncertainty; overlapping collection does not explain that gap. Background allocation/sweeping, OS descheduling and host contention remain unisolated.

The earlier powered110k collapse remains a real user-visible failure with invalid generator timing; this run does not exonerate application code or establish its cause. The next distinction needs wire-response timestamps plus OS scheduling/wait samples, or an independent external Linux native client. These incomplete diagnostic measurements support no capacity or rank claim.

Only completed saved files were read. No Docker, database query, build, benchmark or frozen-file change was performed by this analysis.
