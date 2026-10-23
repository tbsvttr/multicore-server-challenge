# Isolated leader2 prototype: bounded, age-ordered read admission

This candidate hardens source-confirmed amplification paths. It does not establish the cause of the 110k-user collapse, a capacity gain or a ranking. Nothing has been built or executed. Leader1, the PR source and v3 evidence remain unchanged.

Only candidates/leader2/server.goose and main.goose differ from leader1; 34 other copied source files are byte-identical. Build/binary/cache directories were excluded. leader2-hardening.patch and audit/leader2-static-proof.json identify the current version. Original patches, sources and proofs of superseded unexecuted prototypes remain under archive/leader2-sync64-prototype and archive/leader2-sync4-direct-budget-prototype.

## Reader bound and commit boundaries

PG_READ_GROUPS defaults to 4; 0 disables the group-admission cap. Reader-only READ_GROUP_MAX=4 limits each Sync to four executions. Writer GROUP_MAX=64 and its timer are unchanged. With default READ_BATCH=32 this bounds one reader at 16 submitted executions / 512 HTTP requests, or 3072 HTTP requests across six readers. This is not a four-query/request cap. Cap0 retains Sync4 and the new admission policy; only admission is unbounded.

Pgc.groups increments at close_group (server.goose:303) and decrements on ReadyForQuery before answers (687). Reader selection (340) excludes a reader at the cap. An open group occupies its remaining reservation, giving closed_groups+(open!=0)<=cap; closing Sync asserts that boundary. Every reader append selects an eligible reader first. Short reader Syncs release results, buffers and credits earlier. SQL text and within-statement enrichment/snapshots are unchanged.

Writer send_kept remains direct; writes are not deferred, dropped or replayed by the cap. Fresh post-commit reads join readonly queues with the immutable-ID SELECT already replacing the mutation. Waiting or disconnect cannot restore that committed mutation. Existing complete-Z and rollback/retry response gates remain.

## Fairness and queue ownership

Enqueue_read (412) assigns monotonic per-worker Conn.read_order. All reads join nine local FIFO queues: one direct and eight pooled families. Flat reusable ReadNode values store the full connection tag, queue, and previous/next indices. No database result is cached.

Pool_flush (477) chooses the oldest eligible direct head or pooled-family head. A pooled step dispatches one batch, then compares ages again, until reader capacity is full or no work is eligible. Direct FIFO and within-family order remain. Each SQL batch/ordinal is built from its actual admitted members. Coalescing can include younger members of the winning family, but another age comparison follows each bounded batch.

This removes strict direct-priority and fixed-family 0 to 7 starvation without an arbitrary per-flush ratio. New arrivals cannot continually precede an older eligible head. READ_HOLD and the collection window retain their existing eligibility rules; full pools bypass only READ_HOLD, never the reader cap.

Head comparison examines nine heads, not all pending work. Insertion and disconnect/dispatch removal are O(1); batch formation is O(actual members). There is no repeated whole-pool scan/compaction. Stale heads are skipped with full generation and Conn.read_node checks.

Close_conn (153) requires !write plus local read_node ownership before early release. Free_conn (145) unlinks before slot reuse. Unlink_read (429) preserves surviving FIFO order and clears Conn metadata only if both generation and node still match. Submitted requests retain existing dead-slot ownership until their response; they are never canceled by this change.

## Timer/progress reasoning

Pool_blocked (350) gates both pool dispatch and pool_wait_ms (323). With readers full, expired collection timers cannot cause zero-timeout polling; PG replies release capacity. Direct reads are not gated by READ_HOLD or the collection window. After pg_flush, a surviving local direct read implies reader reservations are occupied, so PG/socket events provide its wakeup. Quiet partial pools retain their finite collection deadline when eligible. Open reader groups close/send in the existing pg_flush loop even if later admission reaches the cap.

## Required execution probes before promotion

Use HTTP results, actual frontend PG messages and loop progress. A PG-wire forwarding observer that holds/releases a reader ReadyForQuery supplies deterministic cap witnesses without SQL/schema changes. Counter-mirroring models alone would not validate this scheduler change.

1. Quiet timer: one worker/reader, cap 1, long collection window, fewer than READ_BATCH requests and no extra events. All responses must arrive; no quiet local read may strand.
2. Full gated pool: hold one group's Z, queue several full pools plus directs, and observe no next reader Sync at cap 1 and no busy polling. Release Z and verify all responses exactly once. Repeat cap 4 and 0.
3. Disconnect/reuse: while gated, queue distinct existing/missing slugs, disconnect selected sockets before Bind, then immediately open replacements for different slugs. No abandoned unsubmitted Bind should cross the observer; replacements must return their own 200/404 bodies. Cover every family and enough sockets for slot reuse.
4. Fairness/partial admission: queue older feed/comment/article requests and direct profiles, then sustain new list family 0 and direct arrivals while releasing one group at a time. Every older eligible class must progress. Observe <=4 executions/reader Sync and no cap overshoot.
5. Semantic oracle: 1664 READ cases across duplicate/distinct viewers, flags/counts and empty/missing pages; cap 1/4/0 and READ_BATCH=0/READ_BATCH_US=0 combinations.
6. Fresh CUD reads under cap: fill readers, run UPDATE/favorite/rename races through the independent writer, and verify one committed mutation plus fresh new-ID response after queue drain. Disconnect a fresh-read waiter; no write replay. Run existing rollback/group-commit stress.
7. Full 197 conformance plus bcrypt/NUL/JWT, then declared native comparisons with unchanged controls. Static review is not compilation or performance evidence.

The cap bounds submitted reader work, not the local HTTP queue. It does not cancel submitted queries, unmap arena pages or guarantee a capacity gain. Shorter Syncs and queue bookkeeping may add overhead or reduce useful pipelining; only execution can justify selecting the prototype.
