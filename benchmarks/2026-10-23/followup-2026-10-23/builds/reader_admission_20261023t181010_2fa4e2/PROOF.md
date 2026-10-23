# Reader admission correctness: PASS

The isolated leader2 binary `9016ff93e924c0d94652490ac895d1fbc64153fd9d3ea4b8b52b66ae892c3424`
passed all **26 black-box checks**. This is correctness evidence for an
unpromoted prototype, with no capacity, speed or ranking claim.

The app and transparent PG observer ran as UID 501 with actual NOFILE 200000.
PostgreSQL 18 and the app shared the unchanged 8 CPU/16 GiB/no-swap target. The
fixture used one worker, one reader, PG_READ_GROUPS=1, READ_BATCH=32 and the
normal 5 ms/1 ms collection windows. Only an owned full-seed clone was modified.

- The PG wire trace observed **at most one outstanding reader Sync group** and
  **at most four executions per Sync**; both boundaries were exercised.
- None of 24 abandoned slug hashes appeared in individual or binary-array Bind
  parameters. Replacement connections returned their own article bodies and
  viewer flags. This proves no observed submission of abandoned slugs; it does
  not establish that every abandoned HTTP request was parsed before close.
- All eight pooled families and direct profiles completed while finite mixed
  arrivals continued. The 48 arrival workers completed 1,694 successful requests.
- Favorite and UPDATE committed while their fresh responses waited for reader
  capacity. After release, both returned the new immutable-ID article metadata.
  Each mutation bound once; the unique comment body had exactly one row.
- Original submitted reads completed, fixture rows were cleaned, the clone was
  dropped, and owned app/proxy/probe process groups were stopped. Target PG was
  left idle. All seven power observations reported AC charging at 7%.

The completed observer trace has 771 Binds, 536 query Syncs and 536 matching
ReadyForQuery records, two closed connections and no observer errors. The
independent saved-file verifier replays credits, hashes the original frozen
binary/source/tools, checks the captured wire-prefix digest, and verifies normal
UID/resource/cleanup receipts. Its 1,630 checks pass. It opened no sockets or
database connections. Original source/binary hashes before and after match.

`probe.json` and `result.json` retain the original runtime outcomes; `wire.jsonl`
retains the observation. `verify-saved.py` reproduces `saved-verification.json`
while the original frozen binary remains present. A later text-only export must
retain this receipt and the binary hash even when excluding the executable.
The separate independent verification receipt and complete file-hash manifest
are stored alongside this proof. This checkpoint is newer than published
snapshot `dd941e3`; it does not revise that snapshot or promote leader2.
