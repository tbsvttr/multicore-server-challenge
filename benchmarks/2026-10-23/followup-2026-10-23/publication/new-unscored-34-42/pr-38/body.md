Adds a full-Nim RealWorld Conduit server.

- Direct HTTP/1.1 on `HOST:PORT`; no Nginx.
- Four Nim worker processes per vCPU, each with `SO_REUSEPORT` and one PostgreSQL 18 connection (32 connections on the 8-vCPU box).
- PostgreSQL access through a small libpq binding with prepared statements and session-local `plan_cache_mode`, JIT and parallel settings.
- Page-first list queries, capped pagination fast path, and per-request live SQL. No data/result/JWT caches.
- bcrypt cost 10 via libxcrypt; HS256 JWT via OpenSSL HMAC.
- 197/197 conformance checks pass on both the dev seed and the full 2.35 GB seed locally.
- Small local load smoke passes with 0 errors; this is not an official capacity claim.
