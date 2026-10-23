# Fresh selected-point confirmation (unexecuted)

This runner repeats two held-user points selected from the completed first V4 study in a new block, with Goose source B first and Rust second. It confirms those points; it does not search for a new capacity maximum, establish an official x86 rank, or isolate the cause of any difference.

`cases-DRAFT.json` retains all source, binary, environment, conformance and resource inputs from the frozen V4 source-B configuration. Rust is selected at130000 users. Goose remains `null` until the first study completes and the owner chooses its actual qualified300s hold. The proposed block is conditional on that Goose point exceeding Rust130000. No immutable plan or runtime run has been created.

For each implementation, freeze the exact original binary/source, clone the full original seed once, and start one continuous app session. Run these fixed actions in order:

| Action | Users | Ramp | Measured | Tail |
|---|---:|---:|---:|---:|
| Warmup |10000 |60s |120s |15s |
| Probe | Selected point |60s |60s |15s |
| Hold | Same selected point |60s |300s |15s |

There is a65s minimum connection drain between actions and between implementations. Any invalidity, SLO failure or ineligible phase stops that implementation immediately; there is no fallback count, retry, bracket adjustment or phase reuse. The next implementation may run for the record after cleanup. Cleanup failure stops the entire controller. Both databases are fresh, and each implementation retains its own database/app state across all three actions.

The server remains8CPU/16GiB and the separate external client8CPU/8GiB with no swap or affinity. Client container, actual shard environment and native metadata must all show GOMAXPROCS2. Normal app UID501, nofile200000, exact binaries, PostgreSQL18 durability/full seed and the V4 timing, active-user, histogram, clock, OOM and error gates remain unchanged. The existing dedicated-client cgroup CPU<=75% local policy remains explicit; native whole-VM CPU flags and native qualification remain visible separately. The confirmation does not turn a locally qualified hold into a native-qualified result.

Before preparing a plan, the owner must copy this draft to a new selected configuration, set B to its actual selected first-study hold, and set `first_study_audit` plus `first_study_audit_sha256` to the completed V4 aggregate. Preparation rejects missing/changed references, partial first studies, mismatched binaries/counts, unqualified or non300s holds, reversed-case changes and unresolved placeholders. The completed first-study audit also pins its original plan hash; every effective case descriptor, environment, source/conformance input and client/runtime setting must match that plan, apart from order and the declared confirmation fields. Source B remains labelled prototype until separately promoted. Selected counts may differ, so the confirmation does not make a matched-load latency comparison.

After owner selection and review, the unchanged CLI shape is:

```sh
python3 capacity_controller.py --config /absolute/new-selected-config.json --plan /absolute/new-confirmation-plan.json
python3 capacity_controller.py --plan /absolute/new-confirmation-plan.json --execute
python3 audit/aggregate.py --run /absolute/completed-confirmation-run --out /absolute/new-confirmation-audit.json
```

These are future instructions, not execution receipts. A completed audit reports `confirmed_users`, retains `capacity_users: null`, and sets `capacity_maximum_established: false`. First-study upper/failure bounds remain in their own original record. All failed/invalid phases and native verdicts are preserved.

`v4-origin/` preserves inherited documentation/test receipts as historical V4 material, not results of this unexecuted controller. `v4-origin-sha256.json` pins the source copy; preparation proofs and synthetic tests are under `audit/`.
