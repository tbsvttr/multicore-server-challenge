# Follow-up source observations

No source was ported and no performance conclusion follows from this inventory.
These are candidates for later profiling after the frozen comparison finishes.

Go #37 and Elixir #42 provide useful primary-source descriptions and pinned SQL,
but neither supplies a comparable eight-core,16GiB, five-minute capacity result.
Their lower database CPU in some local comparisons is worth investigating,
while differences in hardware, think time, PostgreSQL version and generator
validity prevent transferring their figures to this comparison.

Two prominent SQL ideas are already present in our frozen B source:

- Tag names use primary-key scalar lookups rather than a per-article join over
  all tags: our `sql.goose:53`, Go37 `sql.go:18`, Elixir42 `sql.ex` tag builder.
- A capped count can test existence of the thousandth row and otherwise count
  the smaller set: our `sql.goose:98`, Go37 `sql.go:68`, Elixir42
  `sql.ex:116`. A statement snapshot preserves correctness under concurrent
  changes. This is not a new missing optimization in B.

Elixir42 conditionally sorts tag names in the application after checking that
the database collation is bytewise (`application.ex:40`). That could move small
sorts out of PostgreSQL, but needs evidence that these sorts matter and a
careful tag-order/escaping oracle. Our SQL currently returns sorted tag JSON;
moving the work may add decoding cost. No gain is predicted or implementation
recommended without profiling.

Go37 reselects the oldest read family and limits one family to half the readers;
Elixir42 uses the less loaded of two reader connections and batches queued work
without a timer. These are concrete scheduler designs, not evidence that either
outperforms B's bounded age-based admission. Preserve the completed frozen
comparison before considering any new configuration/source experiment.

Pinned copies and Git-blob/SHA256 receipts are in the sibling `pr-37/source/`
and `pr-42/source/` trees. This snapshot is for review and attribution; it does
not establish independent conformance or authorize copying without retaining
the applicable source licenses.
