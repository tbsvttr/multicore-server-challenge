# Goose / native primitives / bounded PostgreSQL readers

Front: direct

Goose implements the Conduit API, PostgreSQL wire protocol and SQL, HS256
claim validation, response construction, epoll scheduling and cost-10 bcrypt.
Small C helpers provide our SIMD JSON string writer, per-thread prepared
OpenSSL HMAC and Linux syscall bindings. This fork validation revision adds
bounded reader admission with age-based selection and cancellation of reads
that have not reached PostgreSQL.

This adapts our [single-core Goose implementation](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/143)
and the MIT-licensed asynchronous Conduit/Postgres core from
[XeonFX's PR #31](https://github.com/arjaythedev/multicore-server-challenge/pull/31).
Read batching and shared article enrichment retain attribution to
[Scooter1337's Rust PR #7](https://github.com/arjaythedev/multicore-server-challenge/pull/7).
See [NOTICE.md](NOTICE.md) and [LICENSE](LICENSE) for pinned origins and terms.

## Build and run

```sh
sudo bash install.sh
bash build.sh
DATABASE_URL=postgres://conduit:conduit@127.0.0.1:5432/conduit \
  JWT_SECRET=multicore-server-challenge HOST=0.0.0.0 PORT=80 bash start.sh
```

A clean build compiles Goose from commit
`f605b5a07dd2aa3a5cb3f4c9b14002bd3c9d3d1a`, verifying its source archive by
SHA-256. GCC compiles the generated C and native helpers with optimization
and LTO. Ubuntu 24.04 supplies the dependencies; no application binary is
downloaded. `GOOSE_BIN` may select an already installed matching compiler.
Build and start run as a normal user after the dependency installation.

## Defaults and conditions

| Setting | Default | Purpose |
|---|---:|---|
| `WORKERS` | 2 | Independent epoll loops |
| `PG_READERS` | 3 | Read connections per loop, plus one writer |
| `PG_READ_GROUPS` | 4 | Maximum outstanding Sync groups per reader; 0 disables the admission bound |
| `HASHERS` | 2 | Dedicated bcrypt workers |
| `BCRYPT_BATCH_MS` | 250 | Collection deadline measured from job enqueue |
| `READ_BATCH` | 32 | Maximum members of a compatible read batch; 0 disables pooling |
| `READ_HOLD` | 1 | In-flight admission threshold for an underfull read pool |
| `ARTICLE_BATCH` | 1 | Share overlapping article reads within one execution |
| `WRITE_BATCH_US` | 1000 | Writer collection window; 0 sends Sync immediately |
| `READ_BATCH_US` | 5000 | Pending-read collection window; 0 dispatches immediately |

The default uses **eight PostgreSQL connections**: six readers and two writers.
Configurations exceeding 95 total connections are rejected. `DATABASE_URL`,
`JWT_SECRET`, `HOST` and `PORT` follow SPEC.md.

- Prepared statements pipeline requests. Lists deduplicate compatible page and
  count work before enriching distinct articles. Feeds select each viewer's
  own page before sharing common metadata. Article and comment batches retain
  each member's viewer flags, ordering, missing-resource and empty-page behavior.
  Shared rows and followee sets exist only inside that SQL execution; no response
  or query result is retained for a later request.
- Reader Sync groups contain at most four SQL executions; writer commit
  groups retain their existing maximum of 64. A reader admits at most four
  outstanding groups by default, limiting it to 16 SQL executions awaiting
  ReadyForQuery. With the default batch size of 32, that represents at most
  512 batched HTTP members per reader, rather than a limit on the total local
  waiting queue. Sync completion returns admission credit.
- Eligible pooled families and direct reads are selected by enqueue age. One
  batch is submitted before ages are compared again, so a hot family cannot
  repeatedly refill ahead of older work. Each local queue retains FIFO order.
  Reads waiting locally carry connection-generation tags and removable queue
  nodes. Disconnects remove unsent work; already-submitted SQL is drained normally.
- Quiet reads wake on their collection deadline without another HTTP request.
  A full pool can become eligible earlier, subject to available reader credit.
  The loop waits for the earlier eligible read or writer deadline; reader
  collection does not delay an independent write. Underfull pools can also wait
  for an in-flight execution before dispatch.
- Writers collect compatible work before Sync and wait for commit completion
  before returning success. Article updates and favorite/unfavorite responses
  then reread by **immutable article ID in a fresh statement snapshot**. A
  concurrent slug rename cannot redirect that read, and a read retry cannot
  replay the committed mutation.
- Bcrypt computes only the actual number of occupied lanes, from one to five.
  Every login verifies its stored hash; collection time starts when the job is
  enqueued. Legal embedded-NUL password bytes are preserved, including UTF-8
  passwords at the 72-byte limit. Passwords never enter PostgreSQL text columns;
  other text fields still reject NUL and the password-length rules are unchanged.
  Completed bcrypt replies wait through pipe backpressure and interruptions.
- Each authenticated request computes a fresh HS256 MAC and checks its header,
  expiry and subject. Only per-thread HMAC key setup is reused. Response strings
  use SSE2/NEON escaping while Goose owns JSON structure and validation.
- PostgreSQL 18 uses the supplied schema and cluster settings. The app sets no
  CPU affinity, changes no host tuning and does not restart crashed workers.
  Idle connections remain open within the challenge's descriptor budget.

## Correctness validation

The Linux ARM64 candidate binary `9016ff93e924c0d94652490ac895d1fbc64153fd9d3ea4b8b52b66ae892c3424`
passed the unchanged 197-step conformance suite on both dev and full seeds,
with original seed fingerprints. Additional local checks passed 1,664
baseline/candidate read comparisons, deferred-COMMIT/grouped-rollback and
quiet-timer probes, favorite freshness, update/rename races and legal-NUL
password interoperability against the trusted Go bcrypt implementation.

A separate PostgreSQL wire probe passed 26 checks covering reader credits,
four-execution Sync boundaries, age/FIFO selection, unsent cancellation,
ready-queue retry and quiet dispatch. Its recorded source hashes match this
revision's main.goose and server.goose. That probe is local correctness evidence;
it is not a throughput or capacity measurement.

The unchanged native test commands remain available:

```sh
bash tests/native.sh
bash tests/bcrypt-lanes.sh
```

They cover threaded HMAC/failure recovery, SIMD boundaries, syscall ABI,
reply-pipe backpressure/signals, Goose JWT checks and exact-lane bcrypt.
The [fork-only Ubuntu 24.04 x86 run](https://github.com/tbsvttr/multicore-server-challenge/actions/runs/40001884934)
passed all 18 correctness stages on source `75c4924`, submission tree
`8e821a9ff6f6641ba35aba233cbcffadee81c68c`. It includes a clean pinned
compiler/app build, four unchanged 197-step runs, native/JWT/bcrypt checks,
the read oracle, quiet/commit/rollback/race probes and trusted-Go password
interoperability. The separate ARM wire probe is not part of that CI run.

## Validation scope

This source is a separate reader-admission validation candidate. It is not the
current PR #32 source, and no capacity, performance improvement or rank is
claimed. Local ARM checks and native x86 correctness serve different validation
purposes; performance requires a valid, separately declared measurement.
