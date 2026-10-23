# Runtime candidate correctness probes

These probes are prepared, not executed by the runtime agent. Root starts the server and PostgreSQL in a dedicated disposable correctness DB clone. Use `WORKERS=1 WRITE_BATCH_US=50000` to make writer groups overlap clearly; the extra delay is a correctness stress setting, not the performance candidate default.

`runtime-write-probe.py` uses `BASE`, `DATABASE_URL`, `JWT_SECRET` and normal administrative `PG*` credentials (same pattern as the existing favorite probe). Supply `--out` to retain JSON. It starts no Docker, server or compiler. The database name must identify an owned disposable clone and cannot be a seed/system database.

The probe verifies:

- One authenticated article write completes without any later HTTP request waking the worker; a fresh PostgreSQL connection immediately sees the committed article.
- Sixteen parallel registrations mix duplicate usernames with independent peers. Exactly one duplicate succeeds, expected conflicts return422, and every independent peer returns201. Every201 is immediately checked through a new PostgreSQL connection and real JWT-authenticated API read. PostgreSQL rollback statistics must increase; exact per-Sync membership is not instrumented.
- A temporary deferred constraint trigger for one unique fixture blocks COMMIT on an advisory lock after INSERT RETURNING. The client must receive no HTTP headers while PostgreSQL is actually blocked at that commit, and a new session must see no row. After release, it must receive201 and the row must be committed. This catches responding at statement completion instead of Sync/commit completion.

The temporary trigger/function and exact-prefix fixture users (including cascaded articles) are removed in `finally`; JSON records cleanup verification. This deliberately changes the dedicated test schema temporarily. Never use it in a performance run or against a seed template. Administrative role failures are probe infrastructure failures, not performance evidence.

After this cleanup, run the unchanged `/private/tmp/multicore-research-20261022/favorite-race-probe.py` against the same dedicated clone with `BASE`, `DATABASE_URL`, `JWT_SECRET` and `PG*`. It uses independent fixture names and exercises the blocked concurrent favorite insertion plus fresh post-commit article reread. Its expected count remains2. That probe is compatible with both `WRITE_BATCH_US=0` and the50ms stress setting; no old probe or source change is needed. Together with the original197-step suites and `tests/bcrypt-lanes.sh`, these checks cover the newly delayed commit path without changing uncertain-commit retry semantics.

`WRITE_BATCH_US` is parsed before workers start and bounded to0..1,000,000us. Thus its nanosecond product is at most1,000,000,000 and its ceiling poll timeout at most1,000ms, safely within i32. Zero closes groups immediately; an empty writer returns an infinite idle poll rather than spinning.
