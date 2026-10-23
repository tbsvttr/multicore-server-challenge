# V2 target preparation review and handoff

The new script is prepared and frozen for root execution. This agent performed
only local source reads, edits and AST parsing. It did not execute the script,
Docker, SQL, power checks, sockets, builds, network calls or target preparation.

Frozen script SHA-256:
`3be777e5a3a0d4d962c031fc512c1ccfbcf03c355025839133958213a916b347`.

Preserved original records, unchanged during preparation:

- `prepare-target.py` V1:
  `45884f653a79be773d8d0c41edbc5196c3a6794a903c9cdf2318315c1a468a4e`.
- `target-preparation-20261023/operations.json` failed V1 attempt:
  `54b45fe43c7e0caa5bc7b7ba26769a855bc394e42d6e167eacca1ff2901eb872`.

The runtime CLI requires a new `--out` directory under the host comparison bind.
Optional `--new-target` and `--image` otherwise receive unique defaults. The
output path is translated from `/private/tmp/multicore-comparison-20261023` to
`/comparison` and checked against the inspected original bind mount. Existing
output, target names and image tags are refused. V1 and its failed attempt are
never rewritten.

Before Docker or socket work, six power samples ten seconds apart must all show
the exact AC header and an explicit `charging` or `charged` battery state. The
script repeats a strict power check before startup/commit/create stages and at
completion. Discharging, not-charging and unknown states fail closed.

The original container must initially be stopped; an unexpected running
original is rejected without interrupting it. Once this attempt starts the
original, it starts PG18 when needed, records the original settings/resources,
stops PG cleanly and stops the target before committing. The data-directory
guard rejects shared PG-data bind mounts, so a checkpoint cannot silently share
the original database files with the replacement.

The replacement uses the immutable checkpoint image, a unique ownership label,
the same bind mounts, 8 CPU / 16 GiB / zero swap budget / no affinity, and only
the sixteen IPv4 loopback ports 33000–33015 forwarding to 3000. Docker create
and start are separate; a failed ambiguous create can leave only a stopped
container. Original/new snapshots must have identical PG settings and official
source hashes.

Command intent is persisted before execution, followed by output, errors and
timing. Failure cleanup verifies ownership before stopping a replacement and
stops the original only if this attempt started it. Nothing is deleted. Cleanup
failures remain explicit; unreachable Docker cannot be represented as verified
stopped state. Both preserved V1 hashes are rechecked at the end.

Successful `proof.json` uses `status=PREPARED_NOT_BENCHMARKED` and includes
`old_preserved_stopped`, `old_target`, `new_target`, immutable `image`,
`image_tag`, `loopback_ports`, `server_cpus`, `server_memory_bytes`,
`server_budget_matches`, `no_swap`, `no_affinity`,
`original_pg_settings_equal`, and `original_sources_equal`. A failed preparation
retains its proof, operations and preservation receipts. This is preparation
evidence only; it makes no capacity, performance or ranking claim.

Root reviewed the complete script and reported no actionable finding before
requesting the freeze. This agent will not edit the script during root's run.
