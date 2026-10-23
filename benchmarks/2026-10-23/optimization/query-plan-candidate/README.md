# Isolated query-plan alternatives

These are separate copies of `candidates/combined1`. Only `sql.goose` changes
in each production variant. They have not been compiled, queried or benchmarked
by this agent. Parent-owned candidates, PR source and previous results remain
unchanged. Exact hashes are in `manifest.json`.

| Variant | Change | Purpose |
|---|---|---|
| `feed-share` | Select actual per-viewer pages, deduplicate selected IDs, then enrich each article once | Share real overlap inside one live SQL statement without assuming that equal pagination means equal feeds |
| `feed-window` | Shared feed enrichment plus a bounded recent window and exact indexed fallback | Avoid many author-index walks when the newest window contains the complete requested prefix |
| `favorite-split` | Separate favorite count and viewer existence lookup for global/tag pages | Let count use the article-id index without fetching every favorite's user-id heap tuple |

`feed-share-null-shape.patch` is an optional tiny refinement of the delivered
sharing-only variant: preserve original NULL booleans on the synthetic empty
page row. HTTP output already ignores that empty row. The patch was left
separate so the delivered source hash stays stable. `feed-window` includes this
exact NULL shape from the start.

## Why the bounded prefix is exact

The window contains at most the newest 512 article IDs in the current SQL
snapshot. A request may use it only when it yields all `limit + offset`
matching article IDs. Every article outside the window is older than every
article in it, so no outside article can displace that complete prefix. Apply
the request's offset and limit to the prefix to get the same page.

If the prefix is incomplete, the request executes the existing indexed
per-followee page query. No rows are appended to an incomplete prefix, so there
is no duplicate/ordering issue. Zero limits, offsets/bounds beyond 512, fewer
than the required total matches, and inconsistent raw parameter combinations
skip window eligibility. Numeric parameter equality prevents overflow even if
PostgreSQL reorders predicates. Existing inner page cap 100 is preserved by
restricting the fast path to limits 1–100. Counts remain exact capped counts
per viewer. Window rows, followee arrays and enrichment disappear with the
statement; nothing is cached between HTTP requests.

The model check exercises 55,296 cases, including gapped IDs, old-only followed
authors, empty/tiny feeds, limits 0/1/5/10/100/101, deep offsets, 7,800 successful
prefixes and 1,871 eligible-but-insufficient windows that must fall back. This
supports the algorithm argument; it does not execute or prove generated SQL.
Actual full-seed conformance and differential/concurrent SQL checks are still
required. The existing read oracle's dense fixture followers should exercise
successful prefixes; an old-only author outside the latest 512 rows exercises
fallback. Confirm these branches with actual EXPLAIN execution counts rather
than infer branch coverage merely from passing HTTP responses.

## Query-plan diagnostic

Use the actual `export-sql.goose` helper from `sql-candidate` to dump each
variant's generated PREPARE definitions. Then, outside any native load trial,
run `compare-prepared.py` inside the target with the normal fixture PG*
environment:

```sh
python3 compare-prepared.py --baseline combined1.sql --candidate feed-window.sql \
  --cases feed-cases.json --database conduit_seed --out plans-window.json
```

The script checks exact ordered rows with positional column aliases. It then
performs untimed warmups and alternating AB/BA EXPLAIN ANALYZE executions using
the same generic-plan/JIT/parallel settings as the app. It retains every plan,
buffer/heap witness, stdout and stderr. Failed/incomplete attempts reserve
their output path so a rerun cannot silently overwrite them. These are query
diagnostics, not workload capacity measurements.

`feed-cases.json` includes 2–32 request batches, distinct/repeated viewers,
offsets 0/40/600 and mixed sparse/zero-limit/deep-offset SQL cases.
`favorite-cases.json` tests global pages for anonymous/authenticated viewers,
limits 1/10/100 and recent/deep offsets. Tag cases may be added using an actual
seed tag name. Favorite splitting may help all-visible pages and may lose on
recent dirty pages; choose it only from measured workload evidence.

The narrow `favorites_article_idx(article_id)` cannot supply `user_id` for the
original `bool_or`. The primary key does cover both fields, so heap access is
not logically unavoidable for every possible plan; the actual chosen plan is
what matters. PostgreSQL also checks visibility-map state before an index-only
scan can avoid heap visits. See the official [index-only scan documentation](https://www.postgresql.org/docs/18/indexes-index-only-scans.html)
and [multicolumn/skip-scan documentation](https://www.postgresql.org/docs/18/indexes-multicolumn.html).

Saved earlier feed-count plans always ran old before new and the old viewer-1
plan includes cold reads. Their timings establish plan observations, not a
clean percentage speed claim. The alternating warmed comparison here is
intended to avoid that bias.
