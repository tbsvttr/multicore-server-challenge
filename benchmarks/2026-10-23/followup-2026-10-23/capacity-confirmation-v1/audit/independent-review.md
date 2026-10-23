# Independent selected-point confirmation review

Read-only source review against frozen `capacity-v4`; no controller, test,
Docker, SQL, build or load execution, and no active capacity raw files read.
The draft remains unexecutable while B's selected count and the completed
first-study audit/hash are null.

No actionable finding remains in the final reviewed source.

## Resolved finding: bind first-study configuration

The initial snapshot's `capacity_controller.py:43–75` bound the two binary hashes, selected held
counts, completed first-study audit, 300-second qualification and conformance.
It did not bind either case's `env` or the common effective benchmark/runtime
configuration to that first study. For example, changing
`cases[0].env.READ_BATCH_US` after selecting the reference does not affect
`validate_confirmation`. The subsequent phase audit checked execution against
the changed new case (`audit/evidence.py:61–64`), rather than against the first
study. Likewise, a supported CPU-scope or native/client setting can drift
without the reference gate noticing.

The final source closes this gap. `confirmation_inputs`
(`capacity_controller.py:43–51`) compares all common effective settings and
complete case records by name, omitting only declared documentary/reference
fields and selected counts. The original V4 plan is bound to its completed
audit's `raw_input_sha256["plan.json"]` at lines 82–92. Search overrides are
rejected at lines 59–60. The same validation runs before preparation, execution
and aggregate qualification. The two helper defaults normalize only their
existing identical effective values.

The **current draft itself has no runtime/case drift** relative to
`profiles/capacity-v4-sourceB-config.json`: complete case records match after
removing `confirm_users` and normalizing order. Common settings also match;
only the intended mode/reference/scope/note fields and removal of inactive
search bounds differ.

## Preserved behavior

- `confirmation_actions` (`capacity_controller.py:34–40`) fixes exactly one
  10k warmup, one selected-point probe and one same-count hold. The unchanged
  protocol specifies 60/120/15, 60/60/15 and 60/300/15 seconds respectively,
  with 65-second drains between phases.
- `run_case` (`capacity_controller.py:373–444`) clones and starts once per
  case, keeps the continuous session through its three phases, stops on any
  non-PASS or non-true eligibility, and has no retry, stepdown or phase reuse.
  Cleanup failures abort before another case can start; an ordinary failed
  case can be followed by the other declared case.
- The phase driver, native command/runtime witnesses and outer resource
  lifecycle are unchanged from V4. `search_policy.py`, `audit/evidence.py`
  and `audit/primitives.py` are byte-identical to V4, preserving timing,
  active-user, clock, histogram, error, SLO, process, memory, durability and
  client-cgroup gates. Local and native qualification remain separate.
- `audit/aggregate.py:131–164` independently checks the fixed action sequence,
  prohibits phases after failure, retains every started phase, and requires
  all three phases plus conformance for confirmation. It reports
  `confirmed_users`, keeps legacy `capacity_users` null, and explicitly sets
  `capacity_maximum_established=false`. It cannot produce a new maximum or
  failure bound from this fixed block. Its additional case-start receipt at
  lines 36–40 checks the declared B→Rust prefix, rejects repeated starts, and
  requires exactly one start for every present selected-case directory. Thus
  complete artifact directories cannot qualify without their case-start
  receipts. The final README and DELTAS preserve the unexecuted/selected-point
  scope and are hashed with the reviewed source.

Hashes identify the exact reviewed snapshots in `independent-review.json`.
