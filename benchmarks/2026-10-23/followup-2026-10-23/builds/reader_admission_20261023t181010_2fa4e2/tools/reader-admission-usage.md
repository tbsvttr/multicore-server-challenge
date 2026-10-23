# Reader admission regression probe

Preparation only so far. The script has not opened sockets or queried PG during
its preparation. This is a bounded correctness fixture, not native performance
or capacity evidence. It never builds or starts the application.

Use a dedicated `mc_pair_...` clone and an app with no other HTTP traffic. The
recommended stress configuration is `WORKERS=1 PG_READERS=1 PG_READ_GROUPS=1
READ_BATCH=32 READ_HOLD=1 READ_BATCH_US=5000 WRITE_BATCH_US=1000`. The gate can
hold a reader without blocking the writer's mutation SQL.

For full wire evidence, root starts the optional observer in the app's network
namespace before starting that isolated app. The observer's upstream URL points
directly to PG; it transparently forwards plaintext PGv3. The app's URL uses the
same credentials/database with host/port replaced by the observer listen address.
The probe's admin URL must continue pointing directly to PG.

```sh
python3 tests/reader-admission.py --proxy \
  --database-url "$DIRECT_DATABASE_URL" --listen 127.0.0.1:15432 \
  --wire-log /unique/attempt/reader-wire.jsonl \
  --ready /unique/attempt/reader-wire-ready.json

# Root starts the already-built isolated app against the observer, then:
python3 tests/reader-admission.py --base "$BASE" \
  --database-url "$DIRECT_DATABASE_URL" --secret "$JWT_SECRET" \
  --expected-readers 1 --expected-read-groups 1 --batch 32 \
  --wire-log /unique/attempt/reader-wire.jsonl \
  --out /unique/attempt/reader-admission.json
```

The observer runs until root sends SIGTERM/SIGINT. It records hashes of Bind
parameters and array elements, plus Sync execution counts and outstanding groups;
it does not record plaintext passwords, raw parameters, startup identities or
SQL contents. Preserve its log and readiness output with the attempt. Existing
observer/probe outputs are refused. This observer is not suitable for an SSL or
native benchmark path.

The probe installs two private users, three articles, one tag/follow, and one
viewer favorite. It holds a transaction-level ACCESS EXCLUSIVE lock on `tags`,
fills the reader cap, and witnesses the lock through pg_stat_activity. It then:

- Closes missing-slug requests while all reader reservations are occupied and
  rapidly creates replacement connections with distinct bodies/viewer flags.
- Witnesses favorite and article UPDATE commits through independent SQL while
  their post-commit readonly responses remain pending. A comment201 response
  demonstrates the writer still progresses; its unique body has one row.
- Queues all eight pooled families plus direct profiles, adds finite sustained
  mixed arrivals, releases the gate, and verifies progress and correct bodies.
- Verifies abandoned slugs never occur in single or batched Bind parameters,
  reader Syncs contain at most four executions, the configured group cap holds,
  a four-execution boundary was exercised, and favorite/UPDATE each bound once.

The absence of an abandoned Bind proves no DB submission; application parsing
of every abandoned HTTP request is not directly observable. An immediate404
marker and a short settling interval establish event-loop progress before the
disconnects, and many connection replacements stress slot reuse.

With `--wire-log` omitted, the same HTTP/DB checks run, but output explicitly
labels cap and abandoned-Bind absence as unproven. Such a result must not be
reported as a wire-level cap proof. Cap0 is intentionally not accepted by this
bounded-cap probe; existing conformance/oracles cover that compatibility mode.

All HTTP drain deadlines, SQL statements, transaction readiness and arrival
workers are bounded. Cleanup releases the held transaction before deleting only
the unique fixture rows; it checks private users and tag are gone. Failed
attempts retain a JSON report and cleanup errors. Root owns proxy/app lifecycle.
