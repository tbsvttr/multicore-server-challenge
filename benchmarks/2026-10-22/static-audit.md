# Static review of pinned Goose PR #31

Scope: `43e0919ae5b693c1d3c1e8828b74bb774ef92ee0`, retained under `pr31-source/`. These findings are code inspection, not runtime proof. No submission source was changed by this agent.

No cross-request result cache was found. The read pool holds unfinished requests and batches them before SQL execution; returned data are released rather than reused by requests arriving later. Tags are also queried, not memoized. JWT verifies the HMAC every time, compares the whole signature, parses alternate header encodings to require HS256, validates exp and optional nbf, and parses sub as a bounded positive decimal string. An exact canonical header comparison is an optimization for a constant header, not a token-verification cache. Native HMAC key state can legally be retained.

The inherited bcrypt implementation uses cost 10 for new hashes, fresh OS random salts and compares all 31 bcrypt digest characters. Stored `$2a$`, `$2b$`, `$2y$` hashes are parsed and their real cost honored. All five lanes perform their full independent rounds. Passwords above 72 bytes are rejected consistently with the conformance suite. Runtime interoperability and malformed input still need validation, especially for any native replacement.

The PostgreSQL receive loop locates a complete ReadyForQuery before `group_done` calls response serialization. Observed SQL errors make the implicit group roll back before retries. Deadlock/serialization failures have a retry limit; other rolled-back siblings are resubmitted individually. Socket EOF exits the process instead of replaying requests with uncertain commits. No restart loop, synchronous_commit off, schema change or host tuning was found. Prepared plans, pools and session jit/parallelism/timeout settings are permitted.

Two issues merit attention:

1. **Likely concurrent favorite-count correctness issue.** `sql.goose` ST_FAVORITE / ST_UNFAVORITE return a corrected count from the statement's original snapshot. To demonstrate: transaction T1 inserts favorites for viewers A and B on an article but leaves them uncommitted; API favorite as A starts, observes neither and blocks on the unique key; commit T1. The API does no insert but returns old count +1, while the committed count is old count +2. The reference insert-then-fresh-read sees both. Use a fresh post-commit read for toggles, as the leading Rust implementation does. This schedule has not yet been executed.
2. **No configured total-connection cap.** Defaults are safe (4 loops × (3 read +1 write) =16), but knobs accept arbitrary positive WORKERS and PG_READERS. Reject any configuration exceeding the allowed 95 connections before spawning threads. Otherwise operator input can violate the runtime contract or hang startup waiting for slots.

`extra-auth-checks.py` provides 39 additional read-only black-box checks for required/optional auth, alternate valid HS256 headers, wrong alg/key, malformed tokens, missing/invalid exp, nbf and subject bounds, plus reusing a token across expiry. Run only after starting an owned seeded server and retain its JSON result. It does not replace the original 197-step suite.
