# Goose multicore validation and local comparisons

This is development evidence for [PR #32](https://github.com/arjaythedev/multicore-server-challenge/pull/32).
There is no official score, established first place, or demonstrated lead over all
other submissions. The [competitor inventory](competitors.md) covers the 27 active
competitors and separates official five-minute results from self-reported probes.

Only Rust #7 has been compared against our server for performance. The portable
PR #31 reference passes correctness checks, but its proposed load comparison was
not executed. Submitted defaults remain four workers with article batching off.

## Final candidate result: not accepted

The two-worker/article-batching experiment completed all six planned attempts.
Five passed; the final Goose attempt was invalidated by about 926 seconds of
wall/monotonic clock divergence and recorded no measured requests. This occurred
despite a temporary host idle-sleep assertion. The required three valid pairs
were not obtained, so the predefined acceptance result is **false**. The proposed
promotion patch was not applied. The PR remains a draft with unchanged defaults.

Partial observations from valid matched pairs 1 and 2 are shown once per
implementation below. These ranges describe those two pairs; they are not a
leaderboard or a completed three-pair result.

| Implementation/configuration | Req/s | p50 ms | p95 ms | p99 ms | Total CPU ms/success | Measured errors |
|---|---:|---:|---:|---:|---:|---:|
| Rust #7, unchanged | 21,109.82–21,179.98 | 0.411–0.423 | 2.569–2.745 | 4.263–4.795 | 0.2066–0.2079 | 0 |
| Goose #32, experimental W2/ARTICLE1 | 21,109.95–21,180.67 | 0.499–0.503 | 1.488–1.491 | 2.991–3.011 | 0.1954–0.1962 | 0 |

Combined target CPU per success decreased by 5.0181% and 6.0277% using the
predeclared sampled-interval metric. Independent full-window estimates decreased
by 5.0584% and 6.0376%. p95 improved by 41.96% and 45.79%; p99 improved by 29.84%
and 37.21%. Median latency worsened by 22.38% and 17.97%. Similar fixed-load
throughput does not demonstrate higher capacity. The invalid third pair blocks
default promotion and a stable three-pair gain claim; it was not replaced.

See the [exact acceptance result](audit/w2-article1-preregistered-result.json)
and [independent audit](audit/multi-audit.md) for every attempt and check. All
earlier valid, invalid, failed and interrupted records remain preserved.

## Conditions

The local target is Ubuntu 24.04 ARM64 on a shared M2 Pro Mac. The application
and PostgreSQL 18 share an eight-CPU CFS quota, 16 GiB memory cap and no swap.
There is no explicit CPU affinity. PostgreSQL uses the published configuration
formulas for eight CPUs and 16 GiB; the schema, seed and benchmark code are
unchanged. The original dev and full seed fingerprints passed.

Four official load-generator processes run in a separate four-GiB container.
The first studies used a combined two-CPU client quota; the separately declared
v3 study uses four CPUs for the clients. They still share the Mac and Docker VM with the
target and unrelated workloads. They use four loopback destination addresses
to stay below per-destination ephemeral-port limits. All resource limits,
native generator verdicts, host pressure, raw histograms and failed attempts
are retained. These fixed-load runs do not follow the official warmup, capacity
search and five-minute hold, and cannot establish an official x86-64 score.

## Correctness

- The unchanged suite passes all 197 steps on both dev and full seeds locally.
- A [native x86-64 fork workflow](https://github.com/tbsvttr/multicore-server-challenge/actions/runs/39834209847)
  also passes a clean build, both 197-step runs, native primitives and pipe
  checks, and 4,000 Goose JWT assertions. This hosted runner is correctness
  evidence, not an eight-core performance run. Its submission source is
  identical to PR head `3e908747`.
- Additional checks cover 39 JWT cases, 1,024 concurrent article responses,
  a deterministic favorite commit race, and 293,966 native assertions.
- The disclosed portable/corrected PR #31 reference also passes all 197 steps
  on both seeds. It keeps pure Goose JSON and HMAC; its portability and common
  correctness repairs are recorded in [its manifest](pr31-reference/manifest.json).

## Article batching experiment

All six 10,000-user attempts passed with zero measured errors. This experiment
compares the same candidate binary with `ARTICLE_BATCH=0` and `1`: three matched
pairs, 60-second ramp, 60-second measurement, 15-second tail, fresh full seed per
attempt, normal think time. It is not a comparison against another submission.

| Pair | CPU per success, on versus off | p95 change | p99 change |
|---|---:|---:|---:|
| 1 | -7.035% | -10.334% | -18.664% |
| 2 | -1.095% | -1.800% | -1.279% |
| 3 | +0.330% | +0.838% | -1.294% |

The geometric mean CPU reduction is 2.653%, with one regression. The predefined
five-percent, consistent-improvement screen was not met. `ARTICLE_BATCH` remains
off. The [independent audit](audit/paired-audit.md) and every raw attempt are
retained, including the separate correctness-only smoke run.

## Invalid 80,000-user setup attempt

The first Rust attempt in `multi_pair_20261022t190313_9c13b1` reported widespread
timeouts and repeated `accept: Too many open files`. Docker's descriptor limit
was 200,000, but the common `runuser` launcher reset the soft limit. A separate
reproduction measured 1,024/200,000 after `runuser`, versus 200,000/200,000 with
the corrected common `prlimit` wrapper. The old live Rust process limit was
not directly captured. The original native FAIL_SLO result and server log are
preserved; this is invalid infrastructure, not evidence that Rust is slower.
The following Goose attempt was interrupted and remains incomplete.

The new launcher records the actual application PID, UID and process
descriptor limits before measurement and after load. A separate health-only
verification passed for all three binaries as UID 501 with both limits set to
200,000 and successful responses on all four destination addresses. The first
inspector-permission failure is retained separately. No submission code changed.
The original tool files, plans and attempt records remain available in the
[launcher evidence](nofile-v2/launch-verification-2/result.json).

## Generator-limited two-CPU client study

The corrected v2 launcher verified the required actual process limits, normal
UID, health and memory conditions in both completed arms. Both arms were
generator-limited. Rust recorded zero measured errors but failed the native
latency thresholds; Goose recorded 21,046 measured errors and also failed the
latency thresholds. Their native results remain visible in
[the independent audit](audit/multi-audit.md), and neither supports a clean
performance comparison. The third attempt was interrupted; three other planned
attempts were not started.

The client cgroup hit its full two-CPU quota during the ramp-to-measurement
transition. Goose's measured average was 85.5% of that quota, exceeding the
predeclared 75% client limit. The study was stopped to correct client capacity.
A separate v3 plan assigns four CPUs to the load container. The application and
PostgreSQL retain the same combined eight-CPU / 16-GiB budget, and all binaries,
application settings, workload arguments and validity thresholds are unchanged.
All old tools, plans, completed and interrupted attempts remain available.

## Controlled competitor comparisons

The default-configuration v3 Rust comparison completed all six attempts.
Five passed with zero measured errors; one Goose attempt recorded no measured
requests after a roughly 350-second wall-clock jump over one monotonic second.
That clock-invalid attempt remains in the record. Only pairs 1 and 3 provide
valid comparisons.

There is **no stable overall improvement** with the submitted defaults. Goose
application CPU per success is about 17% lower in both valid pairs, but combined
app-plus-PostgreSQL CPU per success is 6.706% higher in pair 1 and 0.760% lower
in pair 3 (geometric mean 2.905% higher). Tail latency also changes direction:
Goose p95/p99 are 18.415/4.055 times Rust in pair 1 and 0.431/0.522 times Rust
in pair 3. Fixed-load throughput is essentially equal. The
[independent report](audit/multi-audit.md) retains every attempt and full metric
details, including component-counter limitations.

A separate [configuration experiment](proposed-w2-article1-v3/README.md) changes
only `WORKERS=2` and `ARTICLE_BATCH=1`, reducing PostgreSQL connections from 16
to 8. Full-seed conformance passes all 197 steps with the exact same binary.
Its predefined acceptance requires three valid, zero-error pairs, at least 5%
lower combined target CPU per success in **each** pair, and no paired p95 or
p99 regression. It completed with the unaccepted result documented above.
This was a configuration screen, not a capacity or first-place claim. Defaults
remain unchanged. The [PR #31 comparison plan](proposed-pr31-w2-article1-v3/README.md)
is prepared only and was not executed; it cannot substitute for the failed
Rust-study acceptance.
