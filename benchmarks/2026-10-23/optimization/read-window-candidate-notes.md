# Bounded pending-read collection candidate

This isolated copy of combined1 changes only main.goose and server.goose. The
default READ_BATCH_US=0 keeps immediate pool dispatch and the existing writer
poll timeout. Positive values up to1,000,000 microseconds enable collection of
currently pending HTTP requests, with no retained query results or data cache.

The first request entering an empty pool records a monotonic timestamp.
Additional requests do not move its deadline. The pool flushes at the deadline
or at READ_BATCH requests, while preserving the previous in-flight gate below
that maximum. Clearing the pool resets the timestamp. READ_BATCH=0 continues to
bypass pooling.

The loop polls until the earlier eligible read or writer deadline. An expired
read deadline is disabled while in_flight reaches READ_HOLD and the pool remains
below READ_BATCH. A PostgreSQL reply changes that gate and wakes the loop. This
prevents an expired but ineligible pool from forcing repeated zero-time polls.
Quiet eligible reads get a timer wake even if no more sockets become active.

With READ_BATCH_US=0, the added arrival timestamp branch and pool delay branch
are both skipped. pool_wait_ms returns-1, so poll_wait_ms returns the original
writer_wait_ms result. Existing dispatch, grouping, response, rollback and
commit gates are unchanged. This is source-level reasoning, not a completed
runtime test.

No build, Docker operation or benchmark was run while the measured combined2
profile was active. Root will independently review, build, test a quiet read,
run the full197 suite and the1,664-request oracle with READ_BATCH_US=5000 before
profiling200/1000/5000 microseconds. The manifest proof and review-state table
are in read-window-candidate-proof.json; the narrow patch is
read-window-candidate.patch.
