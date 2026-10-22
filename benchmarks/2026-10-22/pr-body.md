Add a direct Goose implementation of the PostgreSQL Conduit API. This adapts our [single-core Goose submission](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/143) and the MIT-licensed asynchronous Conduit/Postgres core from [XeonFX's PR #31](https://github.com/arjaythedev/multicore-server-challenge/pull/31), retaining attribution for read batching from [Scooter1337's Rust PR #7](https://github.com/arjaythedev/multicore-server-challenge/pull/7). Pinned source origins and MIT terms are in NOTICE.md and LICENSE.

The changes reuse our SIMD JSON writer and per-thread prepared OpenSSL HMAC, with a fresh MAC and claim validation on every authenticated request. Portable native syscall adapters retain the x86 epoll path and support ARM validation. An optional bounded article-read batch shares common metadata inside one PostgreSQL execution while retaining each viewer's flags; no result survives for later requests.

Also fixes an inherited concurrent favorite-count race by reading the article after commit, retries nonblocking bcrypt reply delivery instead of dropping completed jobs, and rejects configurations exceeding 95 database connections. The default uses 16 connections, no CPU affinity or host tuning, no result cache, and commit-before-response behavior. PostgreSQL configuration/schema are unchanged.

Validation on Ubuntu 24.04 ARM64 Docker/Mac, with the app and PostgreSQL sharing 8 CPU / 16 GiB / no swap:

- Unchanged conformance suite: 197/197 on dev and full seeds; full seed includes ARTICLE_BATCH=1.
- Original full/dev seed fingerprints match.
- 39 additional JWT checks; 1,024 concurrent article responses match singleton behavior across viewers, Unicode, missing articles and committed changes, with observed shared-SQL execution.
- A deterministic blocked-transaction test reproduces the old favorite count of 1 versus committed count 2; the repaired response returns 2.
- 293,966 native assertions plus 4,000 Goose JWT assertions, including threaded HMAC/failure recovery, SIMD boundaries, Linux syscall ABI and reply-pipe backpressure/signals.
- Clean compiler-and-app bootstrap as a normal user: 86.25 s. Goose source is pinned to full commit and verified by SHA-256.

Native x86-64 validation passed in the [fork-only Ubuntu 24.04 workflow](https://github.com/tbsvttr/multicore-server-challenge/actions/runs/39834209847): a clean source build, the unchanged 197-step suite on both dev and full seeds, and native primitive, pipe and Goose JWT FFI checks. The submission Git tree is identical to PR source `3e908747`; validation commit `f57aad71` adds only the fork workflow. This is separate correctness evidence: the upstream check still requires maintainer approval, the PR remains a draft, and no performance score is claimed.

The [measurement record](https://github.com/tbsvttr/multicore-server-challenge/tree/benchmark-2026-10-22/benchmarks/2026-10-22) preserves validation logs, competitor coverage, predeclared comparison plans and every attempted run, including an invalid launcher setup. The completed three-pair 10,000-user article-batching ablation did not show a consistent five-percent CPU improvement, so ARTICLE_BATCH stays off. Controlled competitor comparisons are running; no completed performance lead is claimed.

Only `submissions/goose-native-tbsvttr/` is added. Comparative load measurements are in progress; ARTICLE_BATCH defaults off until those measurements support enabling it. No official score or first-place result is claimed. Local ARM64 results do not establish the official x86-64 five-minute capacity score.
