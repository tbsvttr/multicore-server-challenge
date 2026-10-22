# Proposed frozen configuration experiment: two loops and shared article reads

The unchanged full-seed conformance suite passed all 197 steps at `WORKERS=2 ARTICLE_BATCH=1` before measurement. The existing default-configuration study is complete. This plan declares a separate configuration experiment; its results will be retained alongside that study.

The candidate uses the same Goose binary, SHA-256 `6ab318a0ab9389dc2e77ec6122ff077a93adbcc183c6285c347104e0f734b6c3`. It changes exactly two process settings:

| Setting | Existing study | Candidate |
|---|---:|---:|
| `WORKERS` | 4 | 2 |
| `ARTICLE_BATCH` | 0 | 1 |

`PG_READERS=3`, `HASHERS=2`, `BCRYPT_BATCH_MS=250`, `READ_BATCH=32` and `READ_HOLD=1` remain unchanged. PostgreSQL connections fall from 12 readers + 4 writers to 6 readers + 2 writers, matching the unchanged Rust control's connection count. Rust's binary, settings and source are untouched.

The hypothesis is that fewer independent PostgreSQL backends and denser overlapping reads reduce database work/scheduling overhead, while the existing live article SQL shares repeated metadata inside an execution. Both settings change together, so a positive result cannot identify their separate effects.

The existing study supports investigating database work: Goose's application used about 17% less CPU per request in both valid pairs, while whole-target CPU was inconsistent. The first pair's latency regression is concentrated in a short burst at measured seconds 62–66. Exact PostgreSQL component CPU is withheld when the live process population changes; the raw component sums are only approximate in that case. The saved evidence contains no WAL sync counters, query wait events or PostgreSQL process-role samples, so the cause of that burst is not proven.

## Frozen protocol and acceptance

The v3 protocol is byte-for-byte identical as a JSON object: 80,000 users, four synchronized 20k-user shards, full fresh seed per attempt, think scale 1, 60-second ramp + 60-second measured window + 15-second tail, three pairs ordered AB/BA/AB, shared target 8 CPU / 16 GiB / no swap, no CPU affinity, and the same actual-UID/200k-descriptor checks. This is a local ARM64 fixed-load diagnostic. It is not the official warm-up/search/five-minute protocol.

All six scheduled attempts must be clean, and **every pair independently** must show:

- Zero errors and passing frozen infrastructure/runtime validity checks.
- At least **5% lower whole-target CPU seconds per successful request** than unchanged Rust. The target includes the application and PostgreSQL; app-only CPU cannot substitute for this metric.
- Candidate overall p95 no higher than its paired Rust p95, and candidate p99 no higher than its paired Rust p99.

CPU/request uses the existing reported sampled cgroup CPU average and native successful request rate; its precise formula and sampling limitation are in `acceptance.json`. Invalid or failing attempts remain retained and block acceptance; they must not be silently replaced. Do not average away a losing pair, change criteria after observing results, or promote defaults/claim a win before all conditions hold. Similar closed-model req/s does not establish capacity.

## Files

- `configuration.json`: unchanged Rust case plus the two-setting candidate.
- `plan.json` / `plan.sha256`: frozen protocol with preregistered criteria.
- `acceptance.json`: evaluation contract. Existing v3 does not automatically enforce these additional 5%/paired-latency gates; evaluate them explicitly after the retained attempts.
- `basis.json`: source/binary identity and exact configuration delta.
- `*-source-binary-freeze.json`: original source and binary witnesses.
- `frozen-tools/`, `frozen-tool-sha256.json`, `host-tool-sha256.txt`: unchanged v3 controller/helper code and expected host copies. The controller copies helpers from the evidence root when executing; those copies must still match before execution.

After Root authorizes execution and the prerequisites pass, the existing v3 controller can consume `plan.json` using its explicit `--execute` mode. No new compiler, source, database setting, host setting, protocol scaling or benchmark process is included by preparing these files. Neither this proposal nor a later passing result establishes first place or superiority to every submission.
