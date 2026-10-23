# V4 preparation deltas

This directory is an isolated copy of v3. `v3-baseline-sha256.json` records the
original files; v3 and both frozen P2 diagnostic variants remain unchanged.
`cases-DRAFT.json` is a proposal, not an immutable plan or execution receipt.
Source B remains an unpromoted prototype. The draft is conditional on root's
choice after the P2 diagnosis, and establishes no capacity or stability result.

The proposed cases are exact ARM leader2 `9016ff93…` and unchanged Rust7
`844afb23…`. Both have full 197 receipts; B also has its exact dev 197 receipt.
The draft uses target 8 CPU/16 GiB and external client 8 CPU/8 GiB, no swap/affinity,
100k initial probe, 1.1 growth, 160k ceiling, 16 probes and 4 holds. Warmup remains
10k with 60 s ramp/120s measurement; probes 60 s/60 s, holds 60 s/300 s, tails 15 s,
drain/idle policy, 5% resolution and failure/invalidity transitions are unchanged.

## Explicit two-P client runtime

V3 fixes one P per shard. V4 requires the same explicit GOMAXPROCS2 setting
already reviewed in P2 at every layer:

- Frozen configuration `gomaxprocs_per_shard=2` and `client_env={GOMAXPROCS:2}`,
  with strict type/value validation against protocol `gomaxprocs_per_shard=2`.
- Client container `--env GOMAXPROCS=2`; raw initial/final inspections are
  retained, and the independent aggregate auditor requires matching Config.Env
  in both. Controller.inspect itself checks budgets; runtime environment
  enforcement uses the per-phase witness described below.
- Each saved shard command has exactly one `GOMAXPROCS=2` override.
- A phase captures container environment and actual native process environments
  through /proc before the common start. Unique PIDs and every expected box
  index/run ID must match; each actual environment must report 2.
- Every native raw shard metadata record must report GOMAXPROCS2. A declaration
  alone cannot qualify a mismatched or unwitnessed process.

The native workload binary, users/ID ranges, per-shard 20k ceiling, maximum 8
shards, target destinations, think scale, histogram reconstruction and all
timing/active-user/clock/error/SLO gates remain. The dedicated-client local CPU
policy still requires ≤75% of the declared client quota. Native whole-VM flags
remain visible and cannot be relabeled native-qualified. Genuine lag, sampler
stalls, missing active users and other invalidity stop the case without a bound.

P2's GODEBUG trace setting, PG diagnostic collector, fixed 100k/110k sequence and
diagnostic deadlines are not added to this capacity search. Only its explicit
two-P client control/witness approach is inherited. V4 preserves normal complete
searches and 300-second holds; every case starts with a fresh seed clone and
continuous app session. No earlier phase is reused or selectively replaced.

## Equivalent CPU quota ratios, with period disclosure

Docker changed `cpu.max` from `800000 100000` to `1600000 200000`: both are
exactly eight CPU of quota, but the CFS period can affect scheduling latency.
V4 checks positive numeric quota/period against the exact declared CPU ratio
in both startup/final snapshots and continuous monitors. Wrong ratios in either
direction, zero/negative/unlimited/malformed values remain invalid.

The monitor preserves every raw `cpu.max` sample with parsed quota/period and
the complete period set. Non-100 ms or changed periods add explicit warnings;
before/after target budget values and policy warnings are also exposed in phase
JSON. Such a warning is not a claim of equivalent latency behavior. Memory,
swap, OOM, clock drift, sample coverage/order/gaps, CPU-counter and all native
qualification gates remain unchanged. This correction applies only to new V4
audits. Past v3/P2 raw results and frozen verdicts are never rewritten, and
their other real invalidity/SLO failures are not excused.

## Preparation validation

The inherited 72-test search/controller/audit suite is adapted with explicitly
synthetic P2 metadata/argv/environment witnesses over preserved historical
histograms/timelines. These are unit fixtures, not evidence that old runs used
P2 or passed new conditions. New cases reject mismatches at every two-P layer,
missing/duplicate/wrong-run process witnesses, and missing explicit declarations.
Integrated cases accept a matching 200 ms eight-CPU budget with warnings and
reject an actual higher ratio. Eight additional light synthetic-monitor tests
exercise quota parsing and preserve all other monitor gates.

Temporary unit-test plans are deleted with their fixtures. No final immutable
study plan is produced during preparation. Independent review and test receipts
are retained under audit; execution remains root-coordinated.
