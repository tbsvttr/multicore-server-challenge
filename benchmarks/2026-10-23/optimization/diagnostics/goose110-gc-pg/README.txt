DIAGNOSTIC ONLY — prepared, not executed.

This isolated copy of the reviewed v3 runner uses exactly one unchanged Goose7a7/native886 session: standard 10,000-user warmup (60s ramp,120s measure,15s tail),100,000-user probe and110,000-user probe (each60s ramp,60s measure,15s tail), with65s minimum drain between phases. One fresh full-seed database is retained continuously. There are no holds, adaptive search, capacity scores, comparison percentages or rank claims. Raw native classifications remain visible. Native errors or invalid timings are not rescued.

Application source/binary/env remain the powered-plan case byte-for-byte, including WORKERS2/PG_READERS3/HASHERS2/ARTICLE1/read5ms/write1ms. App+PostgreSQL share8CPU/16GiB with no swap/affinity, app normalUID and nofile200000. The separate native client retains8CPU/8GiB, GOMAXPROCS1 and exact native886 binary. GODEBUG=gctrace=1 is newly declared and recorded in Docker/exec arguments and actual /proc environment witnesses; all GC logs stay in box*.log.

Read-only PostgreSQL collection is new diagnostic overhead: one short observer connection/sample at1Hz, plus validated before/after snapshots. It uses explicit Unix peer postgres auth, strict owned mc_pair_* database names, query hashes/family labels rather than SQL text, active conduit waits/ages/blockers, pg_stat_database and pg_stat_checkpointer. Each sample has a3s client budget and owned process-group cleanup. The observer adds transactions to that database's commit/rollback counters; sample/error counts must accompany interpretation. No exact application-only transaction rate is claimed. Collector samples/owner/done/exit receipts are retained, and instrumentation_valid=false preserves partial/failed collection.

Before traffic, both the one-shot sample and the continuous collector's first sample must be ok, the target DB must match and version must be PostgreSQL18. Common native start time is assigned only after those observers are ready. The collector has a fixed max duration and stop file; owned exact script/output matching provides TERM/KILL fallback. Existing lifecycle helpers preserve bounded app/database cleanup. All tools/config hashes are fixed by plan preparation and checked before execution; original source config is copied to the evidence directory. Outputs refuse overwrite.

Root prepares the final immutable plan after reviewing this package:
  python3 capacity_controller.py --config config.json --plan plan.json

Only after the current control is fully stopped, on AC power with idle target, root can execute:
  caffeinate -is python3 capacity_controller.py --plan plan.json --execute

The driver verifies AC power before runtime operations, captures awake assertions, and rejects an already-listening target before PG snapshots. It needs the existing owned target and evidence mounts; no new image or rebuild is needed. Execution writes a new optimization/diagnosticgoose110_TIMESTAMP_SUFFIX directory. Preparing/AST checking does not call Docker, psql, builds or load.

The source delta is diagnostic-delta.patch. search_policy.py and audit/evidence.py/primitives.py are byte-identical copies; the capacity aggregation module is deliberately absent. Independent read-only driver/collector review: GO. SQL/auth preflight has not been executed; the validated pre-traffic snapshots will fail early if unavailable.
