Adds `submissions/go-raw-kimmotamio/`. **Front: direct.**

Go 1.27.2, `pgx/v5` (`pgconn` only), no web framework.

- Own HTTP/1.1 server on `net`, one goroutine per connection, one write per response.
- Batched reads: requests of the same kind that queue while all read connections are busy go out as one `LATERAL`-over-`unnest()` statement; each request's rows come from its own execution of its own query, tagged with its ordinal. No timer; batches grow only under load.
- Group-committed writes on separate connections (one extended-protocol batch, one `Sync`, one WAL flush); every response waits for the commit; a failed group is rolled back by Postgres and retried one request at a time.
- Reference SQL with the page of ids cut before the per-article work; session-level `SET`s only.
- Own bcrypt (cost 10, `$2a$`) with the Blowfish key schedule interleaved over up to four hashes; tested against `golang.org/x/crypto/bcrypt` in both directions.

Passes `test/run.sh` 197/197 locally. Details, rules compliance and local numbers are in the README.
