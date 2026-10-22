# Independent local paired-load audit

These are saved ARM64 Mac/Docker diagnostics. No official score, capacity limit, #1 rank, or win over all competitors is established.

## pair_20261022t173322_6500cd

Status: **PASS_LOCAL_EVIDENCE**. Scope: local ARM64 Mac/Docker correctness-only modified-duration smoke.

| Attempt | Result | Req/s | p95 / p99 ms | App / PG / total CPU % of8 | Total CPU ms/success |
|---|---|---:|---:|---:|---:|
| 01-p1-article_on | PASS | 265.600 | 2.169 / 3.001 | 0.449 / 1.789 / 2.350 | 0.708 |

CPU seconds are bracketing 1Hz counter interpolation estimates. Total is target cgroup; app/PG are live-process sums and withheld on population change. PG RSS sums double-count shared pages; combined memory is cgroup memory.current.

Feature screening: **KEEP_DEFAULT_OFF_INSUFFICIENT_OR_INCONSISTENT_GAIN**.

Pair1: unqualified; retained without replacement.

## pair_20261022t184101_5d7ef2

Status: **PASS_LOCAL_EVIDENCE**. Scope: local ARM64 Mac/Docker fixed-load comparison; not an official score or capacity search.

| Attempt | Result | Req/s | p95 / p99 ms | App / PG / total CPU % of8 | Total CPU ms/success |
|---|---|---:|---:|---:|---:|
| 01-p1-article_off | PASS | 2,662.633 | 0.658 / 1.018 | 3.290 / 5.405 / 8.729 | 0.262 |
| 02-p1-article_on | PASS | 2,662.783 | 0.590 / 0.828 | 3.181 / 4.912 / 8.115 | 0.244 |
| 03-p2-article_on | PASS | 2,666.467 | 0.600 / 0.849 | 3.079 / 4.987 / 8.114 | 0.243 |
| 04-p2-article_off | PASS | 2,666.467 | 0.611 / 0.860 | 3.079 / 5.087 / 8.203 | 0.246 |
| 05-p3-article_off | PASS | 2,630.250 | 0.597 / 0.850 | 2.815 / 4.891 / 7.754 | 0.236 |
| 06-p3-article_on | PASS | 2,630.317 | 0.602 / 0.839 | 2.823 / 4.916 / 7.779 | 0.237 |

CPU seconds are bracketing 1Hz counter interpolation estimates. Total is target cgroup; app/PG are live-process sums and withheld on population change. PG RSS sums double-count shared pages; combined memory is cgroup memory.current.

Feature screening: **KEEP_DEFAULT_OFF_INSUFFICIENT_OR_INCONSISTENT_GAIN**.

Pair1, on versus off: RPS +0.006%; p95 -10.334%; p99 -18.664%; total CPU/success -7.035%.
Pair2, on versus off: RPS +0.000%; p95 -1.800%; p99 -1.279%; total CPU/success -1.095%.
Pair3, on versus off: RPS +0.003%; p95 +0.838%; p99 -1.294%; total CPU/success +0.330%.

