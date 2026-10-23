# Narrow CUD/input correctness review and isolated fixes

The reviewed base is `candidates/sharetimer`. No calibration source, Docker,
server, database or benchmark was changed or executed by this review. The
isolated `article-update-fix` copy changes only `sql.goose`, `routes.goose` and
`http.goose`; bcrypt, JWT, scheduling, compiler flags and dependency versions
remain byte-identical. Hashes and 22 static checks are recorded in
`article-update-fix.json` and `article-update-fix-static-proof.json`.

## Auth and bcrypt findings

GET `/api/tags` must ignore even an invalid Authorization header. It is a
no-auth endpoint in SPEC, and the unchanged conformance suite explicitly
expects 200 for `tags.list.ignores-auth-header`. Both stock Goose and Rust do
the same. This is not a token-verification bypass to fix. Required/optional
auth routes use `viewer_of` and `jwt_verify`, which compute a fresh HMAC,
check HS256 and expiration for each verification. Only per-thread HMAC key
setup is reused; token results are not remembered.

The 72-byte password cap is also canonical: conformance explicitly expects
422 on registration with 73 bytes, and Rust uses the same bound. All three
route guards remain before the fixed-capacity bcrypt queue copy. UTF-8
multibyte characters count as bytes. New exact lane counts still execute
`1 << cost` rounds independently for every mapped password/salt; generated
hashes use cost 10 and fresh kernel randomness. Verification uses the stored
hash and its cost, with mixed costs dispatched independently. Malformed
stored hashes fail rather than return a remembered result. No job is skipped
to improve performance.

There was one real inherited input difference: applying PostgreSQL's NUL
restriction to plaintext passwords rejected a valid non-empty JSON password
such as `prefix\u0000suffix`. Password plaintext never enters a SQL text
column, and the pure Goose bcrypt implementation uses explicit byte lengths,
not C-string termination. The isolated fix allows NUL only in password UTF-8
validation. Non-password PostgreSQL text fields keep their old restriction;
the non-empty/type/72-byte guards and all bcrypt code are unchanged. Rust
explicitly supports embedded NUL through its byte-oriented bcrypt path.

## CUD findings and fixes

The existing Sync-group code waits for ReadyForQuery before delivering write
responses. It retries known rolled-back groups after a PostgreSQL error and
exits on a disconnected PostgreSQL socket rather than replay an uncertain
commit. These parts remain unchanged.

Two post-mutation read issues remained despite that commit gate:

1. Article UPDATE selected response metadata in the UPDATE statement's old
   snapshot. A transaction can hold the article row lock, insert a favorite,
   then commit while the API UPDATE waits. The response can contain the old
   count/flag even though that favorite is committed before the API mutation
   resumes. SPEC's UPDATE sequence reads the full article after mutation;
   Rust performs a post-commit read by id. The fix returns only owner/id from
   the mutation, retains 404/403 checks, then issues a fresh read after the
   writer group's ReadyForQuery.
2. Favorite mutation already returned an immutable article id, but its
   post-commit read used the original mutable slug. A transaction can insert
   the conflicting favorite and rename the slug while the API waits, causing
   the mutation to commit and the old-slug read to return 404. The fix uses
   the returned id.

Both fixes use appended `ST_ARTICLE_BY_ID=36` with two integer parameters.
Their helpers replace the kept mutation with a direct read and set
`write=false`, so a later read retry cannot replay the committed mutation.
The id read is not sent through the text-slug batching path. Existing
statement ids/types and all other mutation SQL remain unchanged.

## Root execution instructions

These probes are prepared and syntax checked, not executed by this agent.
Use one dedicated owned `mc_pair_` database clone, never a seed template, and
normal administrative PG* credentials in addition to BASE/DATABASE_URL.

`tests/article-update-race.py` uses real row/conflict waits witnessed through
`pg_stat_activity`; it creates no function, trigger or schema fixture. The
update case checks title/body changes, new slug, count/flag freshness and an
immediate GET. The favorite case checks successful read under a concurrently
renamed slug. Baseline `--expect-stale` reproduces count 0/false or the old 404;
fixed mode requires fresh 200 responses. Baseline-reproduction success is
explicitly different from `implementation_correct`.

`tests/password-nul-probe.py --expect-rejected` reproduces baseline 422s.
Fixed mode requires `--go-helper` and tests 13-, 7- and 72-byte passwords
containing NUL/Unicode. It checks full-password 200, truncated-prefix 401,
stored cost 10, and both Goose-to-Go and Go-to-Goose bcrypt compatibility.
The trusted helper is `tests/bcrypt-passwords.go`; run it from the repository's
pinned `bench` Go module, for example `--go-helper go run /comparison/optimization/article-update-fix/tests/bcrypt-passwords.go`.
Non-password NUL and 73-byte registration inputs must still return 422.

The probes retain failed outputs, use unique fixture identities and remove
their users/articles/favorites afterward. Copies are available under both
`article-update-fix/tests` and the root lab `tests` directory. The production
patch and optional new-test patch are separate. Compile, full conformance,
actual race reproduction/fix checks and trusted interoperability remain
required before freezing the final measured source.
