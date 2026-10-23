DIAGNOSTIC P2 ONLY — prepared, not executed.

This is an isolated copy of frozen goose110-gc-pg P1. Original P1 source, plan5890c6dc... and raw data remain unchanged; p1-origin-receipt.json pins them. Application7a7/source23a14e8, native886, the one continuous fresh full-seed session, and the fixed sequence remain identical:10k warmup(60s ramp/120s measure/15s tail),100k and110k probes(each60s ramp/60s measure/15s tail),65s minimum drain. There are no holds, adaptive search, capacity scores or rank claims.

Declared diagnostic change1: native client GOMAXPROCS=2, explicitly in the protocol, Docker container and per-shard exec env, actual /proc witnesses, raw native metadata checks and command audit. GODEBUG=gctrace=1 remains. Client8CPU/8GiB and shared app+PostgreSQL8CPU/16GiB/no swap/no affinity remain. All native lag/active-user/clock/CPU/error guards remain; changing concurrency does not relabel or rescue any prior result.

Declared diagnostic change2: the1Hz PG observer additionally caches blocking PIDs once per app backend and, when a blocker exists, records blocker backend identity/start/database/app/queryhash and compact locktype/mode/granted/relation metadata. Up to100 involved live PIDs and1024 aggregate lock groups are retained with explicit truncation flags. No SQL text or tuple-lock identifiers are emitted. Because observer detail also changes, this is NOT a pure causal P1/P2 concurrency comparison. Observer transactions still contribute to database-wide counters and sample failures remain explicit.

All P1 preflight/cleanup conditions remain: explicit Unix peer postgres auth; strict owned mc_pair_* database IDs; successful before/continuous-ready samples required before common native start+5s; before/after stats; bounded collector/process-group stop; normal app UID and nofile200000; source/config/tool hashes verified before runtime; copied original config; output overwrite refusal; AC-power precondition and awake assertion receipt. A newly prepared plan freezes all current P2 tools.

Root can prepare the immutable plan after review:
  python3 capacity_controller.py --config config.json --plan plan.json

Root can execute only after all builds/tests/other workloads have stopped:
  caffeinate -is python3 capacity_controller.py --plan plan.json --execute

Execution uses a distinct diagnosticgoose110p2_TIMESTAMP_SUFFIX evidence folder. No new image/rebuild is required. Root owns execution. Static preparation has not called Docker, psql, a build or a benchmark. SQL preflight will run only after authorization and fails before traffic if its first rows are invalid.

Independent read-only review: GO for driver/audit/config and collector. Deltas from P1 are saved as individual patches. All Python/generated helper snippets parse; copied search_policy/primitives hashes and original P1 hashes match. This package tests client concurrency and blocker observability; it does not establish application capacity, a performance win or official rank.
