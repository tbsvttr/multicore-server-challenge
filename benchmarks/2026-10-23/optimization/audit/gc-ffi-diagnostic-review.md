# Goose runtime, FFI and memory diagnostic review

The selected server has no tracing collector, stop-the-world GC, or FFI
safepoint handshake. A Goose collector pause cannot explain the observed
110k-user cliff. This read-only source review does not establish the stall's
cause: ordinary queueing, kernel scheduling or memory pressure, database
delays, and the separate Go client's runtime need execution evidence.

Reviewed source: `candidates/leader1`, selected binary prefix `7a7c31f`.
The [build script](../candidates/leader1/build.sh#L8) pins Goose commit
`f605b5a07dd2aa3a5cb3f4c9b14002bd3c9d3d1a` and requires runtime version
`df5f78ce88d4`. The reviewed generated `main.c` SHA-256 is
`6f2712b7d9215032f702ce1839416224bd1012ea5adfbea3078ab06a8d569ebc`.
No Docker, database, benchmark, binary modification or sampling
was performed for this review. The reported timing sequence was supplied by
the parent investigator; active capacity raw files were not opened.

## Allocation and lifetime behavior

`.build/goose.h` is a 39-line sidecar ABI header, not the collector/runtime
implementation. The generated `.build/main.c` embeds the actual runtime:

| Source location | Directly observed behavior | Diagnostic implication |
|---|---|---|
| `main.c:800` | Data stacks reserve address space, commit on touch, allocate with a thread-local bump pointer, and restore scope watermarks. | No heap tracing, object relocation or global collector rendezvous. |
| `main.c:875`, `main.c:881` | Stack registries and program globals are thread-local; each pthread worker receives its own program state. | A native call blocks its caller; no managed-runtime lock causes other workers to wait for that FFI call. |
| `main.c:33979`, `main.c:34615` | Two temporary stack tops are saved before the epoll event batch and restored after it. | Event temporaries do not accumulate across infinite worker iterations. |
| `main.c:34801`, `main.c:34884` | The local read-dispatch group reuses its base and restores its stack top after pool flush. | Batched request-group temporaries do not grow for the lifetime of the worker. |
| `main.c:1707`, `main.c:2005`, `main.c:2159` | Explicit slice-pool free spans form a first-fit B+ tree; allocation/free/regrowth update that tree. | This is explicit reuse, with no deferred full-heap scan or whole-arena compaction. |
| `main.c:1626`, `main.c:1646` | Stack regions use anonymous mmap and are unmapped on thread teardown. | Restoring a watermark/free span does not return its committed pages to the OS. Large virtual reservations are not equivalent to resident RAM. |

The default 2 GiB per-stack reservation is virtual address space
(`main.c:84`), committed on touch; it does not allocate 2 GiB resident RAM per
stack. Region exhaustion is checked/guarded and aborts; it is not handled by a
collector that pauses and then resumes the application.

The application's persistent byte state is explicit in
[buf.goose:5](../candidates/leader1/buf.goose#L5): each event loop owns an arena,
with offset/capacity runs. [reserve:17](../candidates/leader1/buf.goose#L17)
doubles a run when required; the generated `reserve_g` at `main.c:41755`
copies the old run only if it has to move, and zeroes added capacity. It never
relocates the entire arena. [compact:64](../candidates/leader1/buf.goose#L64)
does linear work in the remaining bytes of one buffer.

Real capacity retention exists:

- Connection `msg` and `ctx` runs grow as needed in
  [keep:342](../candidates/leader1/server.goose#L342) and
  [set_ctx:512](../candidates/leader1/server.goose#L512). Reply completion clears
  logical state, but retains those capacities; actual runs are freed in
  [free_conn:133](../candidates/leader1/server.goose#L133).
- [close_conn:140](../candidates/leader1/server.goose#L140) marks an outstanding
  request dead and retains its slot until the underlying answer arrives.
  Client timeout/disconnect therefore does not immediately cancel queued work
  or release that busy connection's runs.
- PostgreSQL input/output capacities remain after `consume` resets their
  lengths. The hot PG receive/flush paths at
  [server.goose:522](../candidates/leader1/server.goose#L522) and
  [server.goose:548](../candidates/leader1/server.goose#L548) do not call `trim`.
- Releasing a run returns its span to the worker's arena. It does not unmap
  those pages. Temporary stack high-water pages also remain mapped.

These properties can raise resident high-water usage and allocation/copy/page
touch work when backlogs grow. They do not, by themselves, establish a
multi-second pause or a periodic 90-second trigger. No such housekeeping timer
was identified in the reviewed server/runtime paths.

## Native calls and queues

The C adapters execute directly on the calling pthread; they contain no
collector enter/leave, safepoint, shared interpreter lock or managed scheduler
handoff.

| Path | Blocking behavior established from source |
|---|---|
| Client receive/send | Accepted sockets use `SOCK_NONBLOCK` at [server.goose:151](../candidates/leader1/server.goose#L151). `native_sys.c:50`/`:54` call recv/send directly. |
| PG connect/auth/prepare | [pg.goose:200](../candidates/leader1/pg.goose#L200) performs blocking startup I/O before the listener/event loop begins. There is no reconnect in the normal request loop. |
| PG steady-state receive/send | PG startup sockets remain blocking, but [server.goose:525](../candidates/leader1/server.goose#L525) and [server.goose:556](../candidates/leader1/server.goose#L556) explicitly pass `MSG_DONTWAIT`. |
| epoll wait | [native_sys.c:75](../candidates/leader1/native_sys.c#L75) waits only that worker, with the computed read/write timer deadline. Kernel events wake it; no global runtime coordination surrounds it. |
| bcrypt reply delivery | [native_sys.c:32](../candidates/leader1/native_sys.c#L32) intentionally polls indefinitely if a nonblocking reply pipe is full. This occurs on a hasher, not on an HTTP worker. The worker's pipe is created `O_NONBLOCK` at [server.goose:692](../candidates/leader1/server.goose#L692). |
| Hash queue | `main.c:3172` allocates/copies a fixed job before taking the queue lock, then holds the mutex only for count/list changes. `main.c:3202`/`:3211` wait using condition variables, which release the mutex while waiting. No bcrypt work or reply-pipe wait occurs inside that queue lock. |
| HMAC | [native_crypto.c:47](../candidates/leader1/native_crypto.c#L47) has a one-time pthread key initialization, then per-thread keyed state. Ordinary verification reinitializes and hashes the current message; it has no periodic disposal/rotation timer. |

Hasher collection has a 250 ms default deadline from enqueue time, and executes
the actual bcrypt lanes on separate lower-priority threads
([bcrypt.goose:479](../candidates/leader1/bcrypt.goose#L479)). A queued job can
wait beyond that collection interval when hashing service is overloaded; that
interval is not an end-to-end request deadline. A blocked full reply pipe would
be evidence that its event loop is not draining replies, or is falling behind;
it does not itself stop both event loops or the other process's Go timers.

## Queueing and event-loop work relevant to diagnosis

The source does not impose a total pending-request bound. The read-pool gate
at [server.goose:372](../candidates/leader1/server.goose#L372) is bypassed when
the pool reaches `batch_max`; a large pool is then fully dispatched in bounded
SQL groups. [put_request:326](../candidates/leader1/server.goose#L326) appends
messages and increments each PG connection's waiting count without a global
cap. `GROUP_MAX=64` bounds one Sync group, not the number of queued groups.
The bcrypt queue's runtime default is `INT64_MAX` (`main.c:3155`), and this app
does not call `qlimit`.

Consequently a latency cliff can be ordinary growing work queues even with
correctly functioning timers and no runtime pause. A SQL statement timeout
does not bound all prior client-side queueing, batching and pipelined work.
This is a functional property, not a finding that this happened in the run.

There is also no per-callback time/byte budget: [pg_readable:522](../candidates/leader1/server.goose#L522)
first receives until a short read/EAGAIN, then processes all complete
ReadyForQuery groups currently buffered. [accept_all:149](../candidates/leader1/server.goose#L149)
drains the listener, and response encoding/delivery runs synchronously on its
worker. A large available backlog can therefore lengthen one loop iteration.
No source-only bound converts this into the observed stall duration. Sampling
worker stacks and progress would distinguish sustained work from native wait.

## Diagnostics available without changing the binary

There is no runtime GC trace environment setting, live heap/arena usage
counter, queue-depth metric endpoint, signal-triggered stack dump or FFI pause
counter in the selected app/runtime. `GS_STACK_STATS` defaults to compile-time
zero (`main.c:98`); [build.sh:42](../candidates/leader1/build.sh#L42) does not
enable it. Even when compiled in, `gs_rt_stats` at `main.c:913` runs on thread
exit and `gs_stack_stats` at `main.c:2854` reports counts/reservations, not live
resident bytes or pause durations. The workers normally never exit.

For an unchanged-binary diagnostic observation, Linux per-thread CPU deltas,
`/proc/PID/task/TID/wchan`/scheduler state, minor/major faults, RSS or
`smaps_rollup`, and the existing cgroup CPU throttling/memory pressure/reclaim
counts can separate running/copying, native waiting and page pressure. Pair
those with PG/socket backlog progress and the separate client's timer-lag
timeline. Stack sampling, if authorized, should be treated as diagnostic work
whose overhead may affect the run; no attachment or sampling was performed
here.

The review rules out a Goose collector/safepoint pause. It leaves actual kernel
or allocator waits, synchronous event-loop work, queueing and shared-host/client
behavior unresolved pending correlated observations.
