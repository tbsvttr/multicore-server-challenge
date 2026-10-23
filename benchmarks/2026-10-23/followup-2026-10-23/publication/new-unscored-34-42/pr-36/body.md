## Submission: `c-libco-ssmurfgg04-gif` — C11 + io_uring engine + libco coroutines, and a calibrated answer to "can anyone beat 100k?"

Companion to our io_uring entry (#35), from the same $12-challenge lineage. Same hand-written engine (io_uring multishot accept/poll, slot-table `(gen, slot)` user_data, hand-written PG wire client with SCRAM-SHA-256, ~30 prepared statements, pipelined Bind/Execute = one round trip per request, 4-lane ILP bcrypt, HS256 with pre-absorbed pads, strict JSON scanner, `Front: direct` on `:80`), now running every request on a **pooled libco coroutine** (Tencent libco, Apache-2.0, vendored and pinned; 64 KiB stacks, LIFO recycle, lazy create; the event loop keeps sole ownership of all I/O — `pg_go()` and `bcrypt_submit()` are the only await points, and when the pool is exhausted requests run the exact pre-coroutine flow inline, so both modes are equivalent by construction).

### Can we beat 100k? A calibrated model

The scored box's numbers on the leaderboard give two calibration points (same box, same workload, CPU shares measured during the scored window):

| entry | users | req/s | app | pg | per-req cost | model says | actual |
|---|--:|--:|--:|--:|--:|--:|--:|
| rust-tokio (#1) | 100k | 26,279 | 20% | 70% | 61 + 213 = 274 µs | 111k | 100k |
| c-iouring (#3) | 84k | 21,262 | 18% | 80% | 68 + 301 = 369 µs | 82.4k | 84k |

The model (`users ≈ 7.6 cores / (0.25 req/s × per-req µs)`) reproduces both entries within 2–11% — and #1's 11% gap is headroom their own p95 (119 ms vs the 500 ms budget) says is real: they stopped at a round number, not at the wall. **The wall is Postgres**, and 100k only needs **≤ 304 µs/req total**.

Our levers, in order:

1. **`SET plan_cache_mode = force_generic_plan`** (session SET; rule 2 explicitly allows it): kills per-Bind re-planning on statements that are all simple index walks. The best C entry measured +41% from exactly this.
2. **Coroutines make cross-request read batching tractable** — coalescing concurrent identical reads into one `unnest WITH ORDINALITY` query within a small window (~2 ms). The goose entries measured −15% PG CPU; their 250 ms batching windows blew p99, which is precisely the failure mode coroutines let us avoid (the window logic is straight-line code, and we cap it far below the latency budget).
3. The engine basics already proven by #35: one round trip per request, depth-capped cross-request pipelining, 4-lane bcrypt (0.5 core at 100k users' 111 verif/s), direct `:80`.

Projection: 111k at #1's own PG efficiency, ~118k with lever 1, ~133k if lever 2 lands as goose's numbers suggest. **Honest caveat:** our per-request PG cost is not yet measured on the 8-core box — GitHub runners (4 vCPU, everything co-located) only prove stability (0% errors at 1k–5k users, no crashes, ASAN-clean under load) and relative regression-safety. The model's calibration against two independent leaderboard entries is what makes the projection credible; the box run is what makes it final.

### Validation before this PR

- Upstream-style conformance: **197/197 checks** on kernel 6.8 (full io_uring + SCRAM-SHA-256, Postgres 18).
- Parallel-runner bench (1k/2.5k/5k users): **0% errors at every level**, server survived all runs.
- Local 42-point smoke across all 19 endpoints (kernel 5.10 epoll fallback): all pass except one harness-idempotency artifact; also exercised the coroutine pool under inline fallback by capping `CO_MAX`.
- Plus a real bug fix that came with the coroutine rewrite: connection teardown used to free `conn_t` while in-flight requests still held `r->c` (dangling pointer on idle-timeout/stall detach); teardown now defers the free until the last request replies.

