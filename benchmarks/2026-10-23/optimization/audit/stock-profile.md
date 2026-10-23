# Stock80k profile audit

PASS_ONE_ARM_LOCAL_EVIDENCE

Native req/s 21222.633333333335; p95/p99 1.876/7.187ms; measured errors 0; recorded timeline errors 0.
Target combined CPU 58.317% of8CPU; client 35.251% of4CPU.
PG samples in native window: 60; backend observations: {'active': 252, 'idle': 708}.

| Query family | Active observations | No-wait active observations | Share of no-wait active |
|---|---:|---:|---:|
| feed_read | 62 | 59 | 33.1% |
| single_article_read | 36 | 27 | 15.2% |
| comments_read | 35 | 23 | 12.9% |
| list_all | 24 | 21 | 11.8% |
| favorite | 18 | 2 | 1.1% |
| list_tag | 17 | 17 | 9.6% |
| create_comment | 13 | 2 | 1.1% |
| list_author | 12 | 10 | 5.6% |
| created_article_readback | 6 | 0 | 0.0% |
| follow | 5 | 0 | 0.0% |
| tags_read | 5 | 2 | 1.1% |
| list_all_shared | 4 | 4 | 2.2% |
| list_all_batched | 2 | 2 | 1.1% |
| unfavorite | 2 | 0 | 0.0% |
| unfollow | 2 | 0 | 0.0% |
| list_favorited | 2 | 2 | 1.1% |
| list_tag_batched | 2 | 2 | 1.1% |
| create_article | 2 | 2 | 1.1% |
| profile_read | 1 | 1 | 0.6% |
| create_article_tags | 1 | 1 | 0.6% |
| update_or_delete_article | 1 | 1 | 0.6% |

Active waits: {"none/none": 178, "LWLock/WALWrite": 15, "IO/WalSync": 22, "Client/ClientRead": 26, "IO/DataFileRead": 10, "IO/WalWrite": 1}

Counts are point-sampled backend occupancy, not request mix, query CPU time, completed-query latency, or causal contribution. No-wait active backends may be running or runnable. Idle query_ms is last-query age, never charged as execution time.

The observed workload at80k is a valid fixed-load diagnostic only; no sustainable capacity, paired gain or rank is proved.
Feed reads have the largest sampled no-wait active backend presence. Article/comments/list work also appears frequently, making those specific SQL paths reasonable optimization experiments.
WAL sync/write waits are observed, supporting a group-commit experiment; the profile does not establish its causal benefit or expected speedup.
No row-lock-type wait was observed in these samples. Brief waits can be missed; absence of samples is not proof of absence.
Most backend observations are idle. That does not imply PostgreSQL has unused CPU capacity or identify a server capacity ceiling.

The read-only PostgreSQL sampler itself consumes resources and is included in target CPU; this is not an uninstrumented capacity run.
Query text can be truncated by PostgreSQL activity tracking; classification uses recognizable captured prefixes and preserves each captured query/hash/raw-line reference.
pg_stat_activity occupancy is sampled, not accumulated CPU or statement latency. query_ms on idle records is not execution time.
Per-process PostgreSQL CPU is withheld when collector/background PID populations change; cgroup total CPU remains authoritative.
Database counter deltas can lag the actual workload. The sampler connects to postgres, so its own transactions are outside these target-database counters, although collector CPU remains inside the target cgroup. Zero blk_read_time with track_io_timing off does not prove zero I/O.
Original full-seed script verifies all7 tables; per-attempt clone independently counted users/articles only.
