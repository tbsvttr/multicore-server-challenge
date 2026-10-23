# Isolated leader2 prototype

This candidate hardens two source-confirmed amplification paths. It does not
establish the cause of the 110k-user collapse, a sustainable-capacity gain, or
a new ranking. Nothing has been built or executed yet. `leader1`, the PR
source and existing v3 evidence are unchanged.

Only `candidates/leader2/server.goose` and `main.goose` differ from leader1;
34 other copied source files are byte-identical. Build/binary/cache directories
were excluded from the isolated copy. `leader2-hardening.patch` and
`audit/leader2-static-proof.json` describe the exact source boundary.

## Reader admission and progress

`PG_READ_GROUPS=4` is a new prototype default; `0` restores unbounded reader
admission. This caps **Sync groups**, including direct and batched reads.
Reader-only `READ_GROUP_MAX=4` limits each reader Sync to four executions;
writer `GROUP_MAX=64` is unchanged. One execution can answer multiple HTTP
requests. At the default READ_BATCH=32 this bounds one reader at 16 submitted
executions / at most 512 HTTP requests, or at most 3072 across six readers.
This is not a four-query/request cap. Writer admission and its batching timer
are unchanged. Read SQL text, within-statement snapshots and result enrichment
are unchanged; read-only Sync boundaries release responses and capacity earlier.

Each Pgc tracks closed groups that have not reached ReadyForQuery. Closing
Sync increments the count; consuming that group's Z decrements it before
delivering its replies. Reader selection excludes a reader whose closed count
has reached the cap. All request appends select an eligible reader first. An
open group therefore occupies a remaining reservation and can close without
exceeding the cap: `closed_groups + (open != 0) <= cap`. The close path asserts
the capped-reader boundary as well.

The hard cap cannot be restricted to pooled reads: direct reads, including
post-commit fresh reads by immutable ID, could otherwise bypass it. These reads
wait in a generation-tagged FIFO when all readers are full. A PG completion
releases capacity. When an active pool also waits, the event loop admits at
most one direct FIFO execution before trying pooled batches, leaving the other
three executions of a new reader Sync available to pooled work. With no pooled
work it drains the FIFO normally. This avoids strict direct-priority starvation
under sustained overload. If immediate direct admissions filled the cap before
flush, a pending FIFO is formed; its next released group gets the same one-
execution allowance. READ_HOLD and the collection timer still gate pools that
are intentionally not eligible to dispatch yet.
The kept message is already readonly, so delaying it cannot restore/replay the
committed mutation. A queued direct read also keeps its original per-connection
one-request-at-a-time ordering.

`pool_blocked()` is shared by `pool_flush()` and `pool_wait_ms()`. A full pool
still bypasses the original READ_HOLD soft gate; it cannot bypass reader
capacity. When all readers are full, no expired read-collection timer produces
zero-timeout polling. PG socket events release the gate. Read and writer groups
that were already opened still close/send in pg_flush as before. At the end of
an event-loop iteration, a local direct read either has been admitted or is
waiting for an outstanding PG group; there is no quiet unsent direct-read
queue with unused capacity and no wakeup.

## Unsubmitted disconnect ownership

The pool now stores the full 64-bit connection generation tag. A disconnected
read that is still only in the pool or direct FIFO has no PG/hasher owner and
can release its connection slot immediately. `close_conn()` explicitly
requires `!write` for this early release. Submitted requests retain the
existing dead-slot ownership until their response arrives; writes are not
discarded, canceled or replayed by this change.

Before pool dispatch, stale tags are removed in stable order. A reused slot
with a new generation cannot inherit the old request. Admitted requests leave
the pool only after a reader is selected; when the cap is reached mid-flush,
the undispatched active remainder is retained. Batch member ordering and SQL
ordinals are built from those actual admitted members, as before. SQL text,
parameters, response decoding and 404 semantics are unchanged.

`pool_dirty` ensures a blocked local pool is not fully scanned on every timer
check/event when no slot was freed or batch admitted. Direct FIFO prefix
compaction is amortized; stale tags never dereference a reused connection
unless their full generation still matches.

## Required execution probes before promotion

These should observe HTTP results, actual PG wire admission and event-loop
progress. A tiny PostgreSQL-wire forwarding observer that can hold/release a
reader's backend ReadyForQuery gives deterministic admission witnesses without
editing application SQL/schema. Do not use only average throughput or assert
the implementation's internal counter values.

1. **Quiet timer:** one worker/reader, cap1, a long read collection window and
   fewer than READ_BATCH active HTTP requests. With no other incoming events,
   every response must eventually arrive after collection; an idle interval
   must not strand local reads.
2. **Full pool, blocked reader:** allow one real read Sync group through, hold
   its Z, then queue at least two full pools plus direct profile reads. Observe
   that the frontend emits no next reader Sync while cap1 is occupied. The
   process should remain nearly idle while gated rather than burn a core on an
   expired timer. Release Z; all active requests must finish with expected
   bodies, once each. Repeat with cap4 and with `PG_READ_GROUPS=0`, which should
   exhibit the old unbounded admission behavior.
3. **Disconnect and slot reuse:** while that reader is gated, submit pooled
   reads using distinct slugs (existing and missing), disconnect selected
   sockets before any frontend Bind is sent, then immediately open replacement
   sockets asking for different slugs. After release, no Bind for an abandoned
   unsubmitted request should cross the observer; replacements must receive
   their own expected 200/404 bodies exactly once. Repeat across all pooled
   families and enough connections to reuse freed slots.
4. **Partial flush:** release room for one final group while more than one
   group's pool remains, mixing every family and duplicate/distinct viewers.
   The observer must show the cap holds across mid-flush admission; the entire
   retained remainder must drain correctly after later Z messages. Run the
   existing 1664-case READ oracle to cover viewer flags/counts/empty pages.
5. **Fresh reads under cap:** fill reader capacity, then run the deterministic
   article UPDATE/favorite/rename races through the independent writer. Verify
   the write commits, its fresh read waits locally, and its eventual response
   has the new immutable-ID metadata. Disconnect one such response waiter:
   after draining, the mutation must have occurred once. Existing rollback /
   group-commit stress must continue passing.
6. **Compatibility/control:** full197 conformance, bcrypt/NUL/JWT tests,
   default/cap1/cap4/cap0 and READ_BATCH=0/READ_BATCH_US=0 combinations. Then
   compare unchanged-source controls using the declared native protocol.

The cap reduces submitted reader work; it does not bound the HTTP local queue,
cancel already submitted queries, return arena pages to the OS, or guarantee a
capacity improvement. It may reduce useful pipelining. Only independent runtime
correctness and native measurements can justify selecting it.
