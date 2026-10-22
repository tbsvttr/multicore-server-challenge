# First corrected v3 pair: transient tail regression

Analysis uses saved files from `paired-multi-load-v3/v3_multi_pair_20261022t193438_99f820`, arms 01 and 02. Both retain native PASS, zero errors, valid actual child UID/NOFILE, health and OOM checks. No Docker, app changes, tuning, or additional experiments were performed.

Goose’s aggregate tail regression is dominated by a burst at elapsed seconds 62–66, immediately after the ramp, plus a smaller event at 105–107. Its per-second p95 during the first burst is 149, 485, 942, 521, and 333 ms. Outside those events, it generally returns to roughly 1–3 ms. Rust has its own shorter shared tail event at seconds 117–118 (p95 140/190 ms). Aggregate tails include all these intervals.

| Metric | Rust | Goose |
|---|---:|---:|
| Requests/s | 21,164 | 21,088 |
| Overall p95 / p99, ms | 3.001 / 97.535 | 55.263 / 395.519 |
| Median of the 60 one-second p95 values, ms | 2.411 | 1.362 |
| Measured seconds with p95 >10 ms | 117, 118 | 62–66, 105, 106 |
| App CPU, cores | 1.501 | 1.242 |
| PostgreSQL CPU, cores | 2.926 | 3.470 |
| Total target CPU, cores | 4.433 | 4.724 |
| External client CPU, cores | 1.324 | 1.481 |

CPU figures are sampled deltas inside the measurement window. They describe this fixed workload, not server capacity. PostgreSQL summed process RSS shares pages across backends, so the large sum must not be interpreted as actual container memory; cgroup sampled target usage is about 9.6 GiB for both, below 16 GiB. Neither target records quota throttling, swap, or OOM.

The transient is shared by read and write endpoints. Direct bcrypt endpoints account for only about 0.1% of requests. Login latency is higher, but its direct contribution alone cannot explain a 5% aggregate tail. This does not rule out indirect scheduling or queue effects from hashing.

| Endpoint | Rust p50 / p95 / p99, ms | Goose p50 / p95 / p99, ms |
|---|---:|---:|
| GET /api/articles/:slug | 0.398 / 1.929 / 87.679 | 0.311 / 56.159 / 389.631 |
| GET /api/articles/:slug/comments | 0.283 / 1.306 / 86.655 | 0.283 / 41.823 / 316.415 |
| GET /api/tags | 0.267 / 1.444 / 94.527 | 0.323 / 51.199 / 382.463 |
| GET /api/articles/feed | 1.757 / 4.639 / 104.447 | 0.800 / 32.175 / 306.687 |
| POST /api/articles/:slug/favorite | 2.479 / 4.607 / 116.927 | 1.033 / 403.967 / 1030.655 |
| POST /api/articles/:slug/comments | 2.285 / 4.069 / 12.839 | 0.908 / 360.447 / 968.703 |
| POST /api/profiles/:username/follow | 2.211 / 3.887 / 11.647 | 0.819 / 401.407 / 980.479 |
| POST /api/articles | 2.423 / 4.363 / 11.031 | 1.090 / 420.607 / 978.943 |
| POST /api/users/login | 145.151 / 241.535 / 285.951 | 211.967 / 395.519 / 862.207 |

Goose has faster median article/feed and write paths; its bad p95/p99 appears across all those paths during the transient. Request-weighted means are 2.49 versus 13.16 ms for reads, 3.62 versus 44.07 ms for non-auth writes, and 152 versus 236 ms for authentication. Writes suffer the largest amplification.

During the burst, Goose target CPU rises to roughly 6 cores while the four-CPU client consumes about 3.5–3.7 cores. Target CPU pressure grows, but there is no target quota throttle. The client records seven throttled periods and 268,211 cumulative task-throttled microseconds in the sampled 62.1–66.2-second span. This is not 268 ms of wall-clock pause; the metric sums tasks. Native shard tick lag remains below 53 ms and their verdicts remain valid. Wake lag reaches 864 ms. This shows shared scheduling stress without establishing which side caused the backlog.

An extra PostgreSQL PID (21923) appears at 65.032 seconds and exits at 69.034, after the latency burst began. A further temporary PID appears at 125.091–126.093 seconds, about 60 seconds later. The monitor records no process command or backend type; background maintenance is plausible but unproven. The persistent total is 25 PostgreSQL processes for Goose versus 17 for Rust, consistent with their respective 16 and 8 application connections plus common background processes.

Host snapshots show no new swapouts during either 135-second arm; swap usage remains 1526.88 MiB. There is compression/decompression activity and small swapin deltas (108 versus 227 16-KiB pages), so the shared Mac remains a limitation. The evidence does not show a multi-second monitor stall or a target memory-limit event.

The saved evidence favors a shared transient involving PostgreSQL/write queues and scheduling pressure over a persistent slow read or login implementation. It cannot identify a particular query, fsync, lock wait, or queue: those timings and PostgreSQL wait events were not recorded. Source inspection can identify candidate mechanisms, but their causes remain hypotheses.

All numeric source fields, endpoint rows, per-shard lag, sampled CPU windows, and PostgreSQL PID changes are retained in `v3-first-pair-profile.json`.
