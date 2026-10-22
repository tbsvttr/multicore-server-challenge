# Rust / Tokio

Front: direct

Rust 1.99.0, Tokio 1.53.2, tokio-postgres 0.7.18, PostgreSQL 18 and mimalloc 0.1.52. Dependencies are pinned in Cargo.lock.

- Direct HTTP/1.1 using httparse, with fixed-capacity buffer free lists, separate 1 KiB request buffers, stack response headers and vectored writes. Buffers are released while sockets are idle. Active request futures are boxed so idle connections retain a small task. Read completion is bounded after the first request byte; idle keep-alive remains unlimited.
- Prepared generic plans, separate read/write connections, and one statement per mutation. Failed connections and their statements are replaced together, without replaying requests. Global and tag pages compute exact favorite counts and viewer membership in one index scan. Article metadata is computed after pagination; API-bounded pages improve generic-plan cardinality, capped tag counts avoid aggregation when the cap is proven, and favorited-page membership is computed once per request. Existing tags are read without unnecessary updates or locks.
- Compatible read queries prefer connections with matching in-flight queries within a bounded distance of the least-loaded connection, with rotating ties and no collection delay. Read actors combine compatible queued reads into one array-parameterized LATERAL query and route rows back by request ordinal. Overlapping global, tag, author and favorited pages share article metadata enrichment within that SQL execution; viewer flags remain per request. Counts are materialized before joining pages. Batches without enough matching page/filter arguments and personal feeds keep the original query. Other reads keep packed Bind/Execute messages with one Sync. Groups contain at most 32 requests with no collection delay; each SQL execution takes a READ COMMITTED snapshot and results wait for ReadyForQuery. No returned data is retained across requests. The vendored tokio-postgres changes drain errors before reuse and preserve upstream licenses.
- Durable group commit: connection-owning actors collect concurrent writes, commit, then release responses. Failed batches roll back and retry requests individually; uncertain commits are never retried. Favorites and article updates read a fresh snapshot after commit.
- Borrowed PostgreSQL text arrays, direct JSON serialization and SSE2 string escaping on x86-64. Fat LTO and one codegen unit.
- Bounded bcrypt work using the Openwall/libxcrypt 4.4.36 core, with fresh random salts and cost 10. Up to four independent hashes are interleaved to hide dependent table-load latency, retaining every bcrypt round. Startup checks compare the interleaved paths against the original core. Embedded NULs use the portable Rust backend.

Every request reads PostgreSQL. Authentication checks signatures and expiry on every use; there are no result, token-verification or password caches. No schema/config changes, CPU affinity or host tuning.

On eight CPUs the defaults are two Tokio workers, six read connections, two grouped write connections and one bcrypt worker. A write group waits up to 1 ms and contains at most 128 requests. Bcrypt collects up to four jobs with a 160 ms collection window. Optional process settings: `APP_THREADS`, `DB_CONNS`, `DB_WRITE_CONNS`, `BCRYPT_THREADS`, `WRITE_BATCH_US`, `BCRYPT_BATCH_MS`, `READ_BATCH_SIZE` (default 32; 0 disables read batching), `READ_BATCH_US` (default 0), `READ_SQL_BATCH` (default 1; 0 keeps individual SQL executions), `READ_ROUTE_SLACK` (default 8; 0 limits affinity to equal loads, `off` keeps ordinary least-loaded routing).

```sh
sudo bash install.sh
bash build.sh
DATABASE_URL=postgres://conduit:conduit@127.0.0.1:5432/conduit JWT_SECRET=... HOST=0.0.0.0 PORT=80 bash start.sh
```

The API and initial SQL build on [cknutson12's MIT-licensed rust-hyper submission](https://github.com/arjaythedev/multicore-server-challenge/pull/1), with attribution retained in LICENSE. The native bcrypt source and its license are documented in native/README.md.

Local full-seed tests on MEGASERVER (Xeon E5-2690 v3), with the app and PostgreSQL sharing an 8-CPU quota and 16 GiB, no affinity or host tuning. In two fresh-database 60-second tests at 100,000 users, read coalescing reached 25,419 and 25,535 req/s: 7.34% and 9.99% above the better adjacent controls. The final read-only build matched 80,000-user controls (21,222 versus 21,222/21,218 req/s), then passed five minutes at 76,000 users: 20,066 req/s, p95 44 ms, p99 414 ms, zero errors, 124 MiB peak app RSS. A five-minute 90,000-user hold missed the latency limits. Generators used separate cgroups on the same physical host, with loopback networking and CPU/port validation; these are local comparisons, not official challenge scores.

Shared article enrichment subsequently improved two fresh-database 100,000-user 60-second tests by 1.41% and 3.19% over the faster adjacent controls, with zero errors. The candidate passed a five-minute hold at 80,000 users: 21,126 req/s, p95 34 ms, p99 57 ms, zero errors and 83 MiB peak app RSS. These use the same local MEGASERVER setup and are not official scores.

Validation: all 197 unchanged conformance checks on both dev and full seeds, HTTP framing/pipelining and request-deadline checks, database-backend and full-cluster restart recovery, concurrent tags/favorites, grouped-write rollback isolation and immediate visibility, release unit tests, Clippy, and native bcrypt ASan/UBSan compatibility checks.

Bounded read-family routing improved two further 100,000-user 60-second tests by 4.38% and 1.71% over the faster adjacent controls, with zero errors. The final default passed five minutes at 80,000 users: 21,151 req/s, p95 25 ms, p99 140 ms, zero errors and 98 MiB peak app RSS. These use the same local setup and are not official scores.

Queued, viewer-independent tag reads share one PostgreSQL execution only when all recipients are already waiting before execution; no result is retained for later requests. Comments compute the viewer followee set within each query. Optional process settings: `READ_TAG_BATCH`, `READ_TAG_ROUTE`, `READ_COMMENT_SET`; startup defaults are READ_TAG_ROUTE=1, READ_COMMENT_SET=1, READ_TAG_BATCH=1.
