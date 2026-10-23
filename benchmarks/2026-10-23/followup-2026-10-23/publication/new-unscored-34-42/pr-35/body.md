## Submission: `c-iouring-ssmurfgg04-gif` — C11 + io_uring, hand-written PostgreSQL wire client

Carried over and rebuilt from our $12-server-challenge entries ([c-iouring](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/112) / [c-libco](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/121)), adapted for the 8-core box, Postgres 18 and the Conduit workload.

**Stack:** zero frameworks — a hand-written io_uring server (multishot accept + per-connection multishot poll, `(generation, slot)` packed into `user_data` so completions can't hit recycled connections), a hand-written async PG wire-protocol (v3) client (SCRAM-SHA-256, ~30 prepared statements, Bind/Execute pipelining = **one round trip per request**), HS256 JWT with pre-absorbed HMAC pads, and a 4-lane ILP bcrypt (`$2a$` Go semantics, verified against libxcrypt and published jBCrypt vectors). Strict JSON scanner, arena per request. Falls back to an epoll loop running the identical pipeline if the kernel lacks multishot io_uring (probed at startup: listen + self-connect + `CQE_F_MORE`), also downgrades multishot accept to single-shot at runtime if rejected. liburing + libxcrypt from the Ubuntu archive, everything else in `src/`. `Front: direct` on `0.0.0.0:80`.

**Design choices aimed at the leaderboard's known bottlenecks** (PG at 70–80% CPU on top entries):

- **Pipelined batches with per-connection depth cap + worker FIFO** — one Sync per request; back-to-back requests from other connections fill the pipe while the current one waits, instead of adding round trips.
- **4-lane step-locked bcrypt** — login bcrypt (~110 ops/s at 100k users) executes 4 hashes in parallel per worker core to cut the 2-core bcrypt bill.
- **`max_connections` budget:** fixed pool well under the 95 cap; no per-request connections.
- **`-O3 -march=native -flto`**, single binary, no allocator churn on the request path.

**Validation done before opening this PR:**

- Upstream-style conformance (postgres:18 service container, dev seed, `test/run.sh` equivalent): **all 197 checks pass** on kernel 6.8 with full io_uring + SCRAM-SHA-256, including the 422/validation edge cases and `Token <jwt>` auth scheme.
- Parallel GitHub-runner load test (6 runners, levels 1000/2500/5000/10000/15000/20000 users + ASAN build under load): **0% errors at every level, no crashes** after fixing a request-ownership double-release caught by ASAN. Absolute latency on these runners is not meaningful (4-vCPU shared runners with loadgen, Postgres and server co-located, CPU pegged at ~100%) — the numbers that matter are the stability/error-rate results until we can run on real 8-core hardware.
- Local smoke suite: 42/42 across all 19 endpoints, permissions, error paths, JWT round-trip and bcrypt verify.

