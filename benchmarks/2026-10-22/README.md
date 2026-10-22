# Goose multicore validation and local comparisons

This is development evidence for [PR #32](https://github.com/arjaythedev/multicore-server-challenge/pull/32).
There is no official score, established first place, or demonstrated lead over all
other submissions. The [competitor inventory](competitors.md) covers the 27 active
competitors and separates official five-minute results from self-reported probes.

## Conditions

The local target is Ubuntu 24.04 ARM64 on a shared M2 Pro Mac. The application
and PostgreSQL 18 share an eight-CPU CFS quota, 16 GiB memory cap and no swap.
There is no explicit CPU affinity. PostgreSQL uses the published configuration
formulas for eight CPUs and 16 GiB; the schema, seed and benchmark code are
unchanged. The original dev and full seed fingerprints passed.

Four official load-generator processes run in a separate combined two-CPU,
four-GiB container. They still share the physical Mac and Docker VM with the
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

## Controlled competitor comparisons

Pending. A clean performance comparison must pass the native generator and
resource checks and have zero measured errors in both arms. Fixed-load latency
and CPU differences will be reported separately from capacity.
