Adds `submissions/elixir-gentcp-chuukwudi/`: Elixir 1.19.6 on OTP 28.5.0.8, **Front: direct**, no Hex dependencies.

**What it is**
- Own HTTP/1.1 server on `gen_tcp`: one small hibernating process per connection, one short-lived worker per request with a preallocated heap (no GC), raw tagged writes to the inet driver.
- Own Postgres wire-protocol client (SCRAM-SHA-256, prepared generic plans, binary results, pipelining).
- Batched reads: same-kind requests run as one `unnest` + `LATERAL` statement, and each read connection sends everything queued as one pipelined round under a single Sync. No timer; batches grow only under load.
- bcrypt cost 10 via a small NIF (Openwall core + 4-lane interleaving, credited in `c_src/README.md`).

**Rules**: no cross-request caching or result sharing (each request's rows come from its own execution; Memoize off), writes committed before responding, bcrypt on every login/register/password change, HS256 signature + `alg` + `exp` checked on every request, session settings only, 13 Postgres connections.

**Checks**
- Conformance: 197/197 on the dev seed and on the full seed.
- `mix test`: 12 tests pass.
- `install.sh` and `build.sh` verified on a clean Ubuntu 24.04 container (arm64).

Local load numbers (not official, shared 6-CPU Docker VM) are in the README.


