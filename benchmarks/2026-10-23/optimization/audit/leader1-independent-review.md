# Final leader1 source review

No actionable correctness or original-scope finding was identified in the
selected `candidates/leader1` diff against stock source `3e908747`. This was a
read-only source review; it did not build, mutate infrastructure or run tests.
It is separate from the root's execution evidence and makes no ranking claim.

- **Timer progress:** [writer deadline](../candidates/leader1/server.goose#L293),
  [read-pool deadline](../candidates/leader1/server.goose#L302), and
  [combined poll deadline](../candidates/leader1/server.goose#L311) wake quiet
  pending work. A pool gated by in-flight work waits for a PostgreSQL reply
  instead of spinning on an expired timer; a full pool retains its existing
  bypass. [Collection/flush](../candidates/leader1/server.goose#L360) keeps
  requests, not prior query results, and clears the collection timestamp with
  the drained pool. Configured intervals are bounded before workers start in
  [main.goose](../candidates/leader1/main.goose#L93).
- **Commit boundary and partial writes:** [pg_flush](../candidates/leader1/server.goose#L548)
  sends only the prefix covered by Sync. Pending-byte consumption subtracts
  exactly the sent prefix, so compaction cannot expose a later unclosed
  writer tail. [group_done](../candidates/leader1/server.goose#L565) still
  delivers responses only after the complete ReadyForQuery group and retains
  known-rollback handling. The reviewed change does not reconnect/replay an
  uncertain committed write or restart a crashed worker.
- **Post-commit mutation reads:** [favorite_committed](../candidates/leader1/routes.goose#L421)
  and [article_update_committed](../candidates/leader1/routes.goose#L439) consume
  immutable IDs, preserve 404/403 distinctions, replace the kept mutation with
  a direct `write=false` read, and avoid the text-slug batching path. A later
  read error cannot replay the committed mutation. The new statement is
  [ST_ARTICLE_BY_ID](../candidates/leader1/sql.goose#L43), with integer parameter
  types at [statement_types](../candidates/leader1/sql.goose#L355).
- **SQL semantics:** [shared_list](../candidates/leader1/sql.goose#L179) keys
  filtered pages/counts correctly; [shared_feed](../candidates/leader1/sql.goose#L217)
  includes viewer and pagination when selecting pages, discovers overlap from
  actual IDs, and keeps per-viewer favorite flags. [batch_comments](../candidates/leader1/sql.goose#L256)
  retains missing-article versus empty-comment behavior, comment order and
  per-viewer follow flags. Empty-page rows and response ordinals keep their
  existing layouts. Materialized data exists only within its SQL statement.
- **Authentication and password input:** [viewer_of](../candidates/leader1/routes.goose#L113)
  still performs fresh [JWT verification](../candidates/leader1/jwt.goose#L48),
  including the full [HMAC update/final](../candidates/leader1/native_crypto.c#L97)
  on repeated tokens. The [no-auth tags route](../candidates/leader1/routes.goose#L167)
  intentionally remains 200 with an invalid Authorization header, as required
  by canonical conformance. [Password validation](../candidates/leader1/routes.goose#L55)
  permits NUL only for length-aware bcrypt inputs; [PostgreSQL text validation](../candidates/leader1/http.goose#L161)
  remains strict. The register/login/update byte caps remain at lines 207,
  232 and 278 of routes.goose.
- **Full bcrypt work:** [constants and typed jobs](../candidates/leader1/bcrypt.goose#L384)
  retain the 72-byte bound and cost 10 for generated hashes. [prepare](../candidates/leader1/bcrypt.goose#L438)
  reads the stored hash/salt for verification; [hasher](../candidates/leader1/bcrypt.goose#L482)
  maps every job to an exact lane or independent cost group. The two/three/four
  lane implementations retain all rounds and do not substitute cached results.
- **Original scope:** the [connection-budget guard](../candidates/leader1/main.goose#L85)
  still keeps the process below 95 database connections. Selected defaults
  yield eight app connections. The changes introduce no schema/cluster
  configuration changes, CPU affinity, extra service or cross-request cache.
  Local ARM results remain distinct from the official x86 benchmark ranking.

The bounded recent-window experiment is absent from the selected source.
No additional tests or source changes were requested by this review.
