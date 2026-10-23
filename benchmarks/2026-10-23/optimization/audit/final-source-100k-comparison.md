# Final-source 100k load point

Independent point audit PASS 27/27; both phases are native- and locally qualified, with zero measured and timeline errors.

One exploratory sequential comparison: 100,000 users, 60-second measurement. Final global run checks remain pending. This does not establish capacity, a stable percentage gain or official rank.

| Implementation | Requests/s | Target CPU ms/success | p50 ms | p95 ms | p99 ms | Errors |
|---|---:|---:|---:|---:|---:|---:|
| rust7 | 26,481.67 | 0.191172 | 0.812 | 15.703 | 78.463 | 0 |
| goose32 | 26,474.17 | 0.160411 | 2.961 | 6.603 | 46.751 | 0 |

At this point Goose used 16.09% less combined app/PostgreSQL CPU per successful request. Its p95 and p99 were lower; its median was higher. Mean latency was 4.459 ms versus 4.148 ms; maximum observed latency was 669.695 ms versus 332.287 ms.

Rust completed 1,588,900 measured requests; Goose completed 1,588,450 (-450, -0.0283%). Recorded page views were 856,065 and 855,981. The five shards share identical RNG seed inputs and user allocations. Observed endpoint/page/session counts differ slightly; there is no full identical request-trace claim.

CPU cost uses full-window sampled cgroup CPU divided by successful requests. It includes both app and PostgreSQL, excludes the separate load client, and remains an estimate from monitored counters. Client CPU averages were 20.29% and 20.53% of the same eight-CPU client quota.

The Goose binary is final `7a7c31fb…` at source `23a14e8…`; Rust is `844afb23…`. These are separate measurements from the earlier `a34…` calibration. Raw hashes, source/environment identities, exact histogram audits and all observed workload-count differences are preserved in the JSON report.
