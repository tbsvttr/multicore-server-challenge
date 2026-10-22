# Local paired-load controller

Prepared only: no Docker action or performance run has been executed by the preparing agent. Run after all compilation and correctness traffic stops, with the target's chosen port free. The controller refuses an occupied port rather than stopping another process. It never stops the target container, touches host sysctls, changes Docker global settings or kills an unrelated container.

Dry plan (no Docker or network):

```sh
python3 paired-load.py --config paired-load-example.json --plan article-10k-plan.json
```

Execute that frozen plan only when the root agent is ready:

```sh
python3 paired-load.py --plan article-10k-plan.json --execute
```

A separate one-attempt smoke plan uses1,000users,10s ramp +15s measure +5s tail, explicitly labeled correctness-only modified duration. It defaults to case1 (the candidate); `--smoke-case0` selects the control:

```sh
python3 paired-load.py --config paired-load-example.json --plan article-smoke-plan.json --smoke
python3 paired-load.py --plan article-smoke-plan.json --execute
```

Preparing or running a smoke plan never changes the six fixed-duration comparison attempts. Infrastructure commands explicitly execute as container root because the inherited image defaults to user bench1001; the actual app starts through `runuser -u challenge` and remains a normal-user process.

The six fixed attempts are A/B, B/A, A/B: each of three pairs contains both arms, with alternating first arm. All attempts are retained; failed or invalid attempts are never replaced. Both arms use the same native run-id within a pair to match the deterministic workload random stream and seeded user ids, while separate fresh database clones prevent sign-up name collisions. Each arm uses full seed, normal think scale1,500k seeded articles,60s ramp +60s measured +15s tail. A65-second drain between attempts lets TIME_WAIT expire without changing TCP settings. The minimum load time is13.5minutes; cloning, startup and five drains bring total execution to about20minutes or more. This omits official warmup/search/five-minute holds and is explicitly a fixed-load diagnostic. At unsaturated10k-user load, similar throughput is expected; latency and app/PostgreSQL CPU are the useful initial signals. It cannot establish #1.

The target must be `multicore-goose-dev-20261022`, with app and PostgreSQL18 together under8CPU/16GiB/no-swap, no cpuset. A uniquely named owned load container uses2CPU/4GiB/no-swap with the target's network namespace. This shares loopback networking but not the server cgroup. Both remain on the same physical ARM64 Mac, contending with its other work. The controller reads the existing Linux ephemeral port range and refuses a count that would exhaust it. Initial config supports1k–20k users on one address; it performs no port-range or host tuning.

Case binary/source paths and environment are configurable. The example isolates ARTICLE_BATCH0/1 using the same compiled binary; it can instead point each case at different credited source/binary snapshots. Every binary is copied into a unique frozen location, hashed and checked before launch. Source files are hashed and archived, excluding compiler/build caches including `.build` and `.deps`. Each server runs as the normal `challenge` user in a new owned process group, with the runtime contract fixed centrally. Only that exact group is stopped. Only `mc_pair_*` database names created by the controller are cloned/dropped.

Evidence lives in `paired-load/<unique run>/`: immutable plan/hash, full container inspect files, source/binary archives and hashes, tool hashes, live PG settings, clone counts, startup logs, raw native generator JSON, native merged output and verdict, exact generator command and app environment, per-attempt assessment,1Hz target/load cgroup and app/PostgreSQL process witnesses, and host memory/swap observations. Read `/proc` RSS sums as diagnostic: PostgreSQL shared buffers appear in multiple processes, so the cgroup memory sample is the correct combined physical budget witness.

Native `lg_limited` is retained unchanged: such a run is INVALID_GENERATOR, never a server failure. Inside Docker the tool reads VM-wide `/proc/stat`, which includes target and other containers. The assessment therefore also predeclares a separate effective-generator check: utilization above75% of the load container's own2CPU quota or a load-cgroup OOM kill makes the attempt INVALID_GENERATOR_CGROUP. This can invalidate a native PASS without changing its native verdict. Missing or incomplete monitor evidence makes an otherwise-passing attempt INVALID_MONITOR under the predeclared3s maximum gap. Native SLO results and all raw counters remain available. Host pressure records are diagnostic, not a retrospective exclusion rule.

The controller is syntax checked and dry-plan checked only. Root should perform a1k-user sanity attempt before this20-minute plan and verify process lifecycle and generated records. Do not report the paired probes as an official score, a maximum user count or a stable5% throughput improvement.
