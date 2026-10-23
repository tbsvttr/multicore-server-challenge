# Closed Rust confirmation: native replay

PASS: 24 independent checks and 639 frozen phase checks. All 75 consumed input hashes stayed unchanged.

| Phase | Users | Ramp / measure / tail | Requests | p95 / p99 ms | Native qualified | Local qualified |
|---|---:|---|---:|---|---|---|
| warmup | 10,000 | 60 / 120 / 15 s | 318,326 | 1.557 / 2.917 | True | True |
| probe | 130,000 | 60 / 60 / 15 s | 2,067,014 | 97.471 / 206.719 | True | True |
| hold | 130,000 | 60 / 300 / 15 s | 10,301,608 | 24.783 / 401.407 | False | True |

The 130,000-user / 300-second hold measured 34338.6933 requests/s with zero measured or full-timeline errors. SLO PASS is retained. All seven native shard CPU averages were approximately 76.390%, above the native 75% whole-VM CPU guard: native `lg_limited=true`, `native_qualified=false`, with each original `box N CPU 76% > 75%` reason preserved.

The predeclared `dedicated_client_cgroup_v1` policy qualifies the hold locally via its CPU-only scope exception. No timer/coverage/active-user failures occurred; the dedicated client's sampled 8-CPU quota utilization was 20.61295%. Warmup and probe qualify under both native and local criteria without an exception. Every saved assessment field matches the raw replay except its initial classification placeholder.

HDR bins/counts/quantiles, statuses, errors, native CPU/timer summaries, clocks, monitor coverage/budgets, health and process witnesses were replayed using the frozen verifier. The retained PG live-PID component warning withholds that component estimate.

This is a Rust-only saved-file phase replay. It does not repeat B or certify whole-pair order/provenance/reference binding. No exact capacity maximum, official rank, code-promotion or causal claim is made.

Detailed checks and file hashes: `confirmation-v1-rust-native-replay.json`.
