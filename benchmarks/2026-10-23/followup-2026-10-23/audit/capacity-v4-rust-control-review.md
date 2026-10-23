# Completed Rust control review

PASS 42/42 independent frozen-auditor replay checks across eight completed phases.

The unchanged Rust 844 control held 130,000 users for 300 s under the predeclared local policy; 135,000 and 140,000 are valid SLO failure bounds. This gives a local 130k–135k interval. Hold p95/p99: 117.951 / 580.095 ms, zero measured and timeline errors. Client cgroup utilization:20.236328782578056% of its 8 CPU quota.

Native qualification remains false: all seven native shard flags are whole-VM CPU >75%. These flags and all original assessments/errors are retained. No target OOM/crash or unfinished terminal VUs occurred.

Goose B remains pending. No whole-study comparison, official rank or official/native-qualified capacity claim is made. Session/source/full 197 identity checks are independently reviewed alongside this replay.

The separate Rust session audit passes 24 checks: the frozen/current Rust 844 binary, 65 archived source files and pinned full 197 log match; one fresh full-seed clone and PID 334 / PGID 333 remain continuous through startup, 16 saved snapshots and 1,437 monitor samples. Seven drains meet 65 s; stop/drop receipts agree. All 197 consumed-file hashes remain unchanged. See rust-v4-session-independent.json.
