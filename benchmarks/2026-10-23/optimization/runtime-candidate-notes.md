# Isolated runtime candidate; not built or measured

The candidate copies only the Goose submission. SQL, routes, original submission files and prior evidence are unchanged. Production compiler flags remain Goose -O2, GCC -O3/-march=native/LTO/NDEBUG; no missed debug configuration was found.

Changes:

1. Writer groups collect for at most the configured monotonic interval before closing with Sync. `WRITE_BATCH_US=1000` is the candidate default; `0` restores immediate Sync closure. The epoll timeout wakes an otherwise quiet worker to close its pending writer group. `sendable` counts only bytes covered by a Sync, so an unclosed writer tail is never sent, even when older closed groups share the output queue. Partial writes subtract exactly the sent bytes. Reads close and flush immediately as before; GROUP_MAX still closes at64. Successful responses still occur only after ReadyForQuery, with the existing rollback/retry and post-commit favorite reread paths untouched.
2. Two, three or four bcrypt jobs run exact specialized interleaved states instead of computing five hashes with repeated dummy lanes. One and five lanes retain the old implementations. Every job still executes its own full cost, salt and key schedule. New tests compare all interleaved lane counts against independent single-lane results at costs4/5/10 with five distinct passwords and salts.
3. Bcrypt jobs record enqueue monotonic time. Workers drain already queued jobs first and age the existing250ms collection deadline from enqueue, rather than granting old queued work another250ms after a worker becomes free. Queue time may still exceed that deadline under CPU overload; no work or verification is skipped.

Root validation required before performance use: build; `tests/native.sh`; new `tests/bcrypt-lanes.sh`; unchanged197-step dev/full suites; deterministic favorite commit race; concurrent writes that trigger a unique violation in a grouped Sync and verify successful peers are retried and visible after response; quiet single write completes with no subsequent traffic; partial PG writes/backpressure do not expose an unclosed tail. Repeat with WRITE_BATCH_US=0 to isolate the writer change when measuring. No claim of throughput, tail improvement or official rank is made.

The changes do not add result/JWT/password caches, alter SQL/schema/PostgreSQL configuration, reduce bcrypt cost, replay uncertain commits, alter affinity or introduce worker restarts. The SQL agent owns a separate composable candidate. No Docker, compiler, server or benchmark was invoked while preparing this copy.
