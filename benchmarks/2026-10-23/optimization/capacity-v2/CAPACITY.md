# Local capacity search

Version 2 is a separate, unexecuted controller with a predeclared external
client CPU quota. The earlier 4-CPU study and its invalid 160,000-user attempt
remain unchanged; their generator failure is not a server capacity bound.

The runner uses the existing native workload on the authorized shared ARM Mac.
It does not produce an official x86 score or prove first place among submissions.
Preparation does not invoke Docker or the network. Only `--execute` starts work;
root schedules execution and wraps it in `caffeinate -i` when appropriate.

```sh
python3 capacity_controller.py --config cases.json --plan frozen-plan.json
python3 capacity_controller.py --plan frozen-plan.json --execute
python3 audit/aggregate.py --run /private/tmp/multicore-comparison-20261023/optimization/capacity_RUN --out /private/tmp/multicore-optimize-20261023/audit/result.json
```

Configuration uses the prior v3 case schema:

```json
{
  "target_container": "multicore-comparison-target-20261023",
  "host_evidence": "/private/tmp/multicore-comparison-20261023",
  "container_evidence": "/comparison",
  "old_host_evidence": "/private/tmp/multicore-research-20261022",
  "native_binary": "/evidence/tools/loadgen",
  "load_cpus": 8,
  "client_cpu_scope_policy": "dedicated_client_cgroup_v1",
  "search_overrides": {"start_users": 160000},
  "load_memory_bytes": 8589934592,
  "port": 3000,
  "jwt_secret": "multicore-server-challenge",
  "cases": [
    {
      "name": "candidate",
      "binary": "/comparison/candidate/bin/conduit",
      "source_dir": "/comparison/candidate",
      "source_revision": "pinned source identity or manifest",
      "expected_binary_sha256": "REPLACE_WITH_SHA256",
      "env": {"WORKERS": "4", "PG_READERS": "3", "HASHERS": "2"},
      "conformance": {
        "passed": true,
        "checks_passed": 197,
        "checks_total": 197,
        "binary_sha256": "REPLACE_WITH_SAME_SHA256",
        "log_host_path": "/private/tmp/path/full-conformance.log",
        "log_sha256": "REPLACE_WITH_LOG_SHA256"
      }
    }
  ]
}
```

Each actual binary hash must contain 64 hexadecimal characters. Preserve the
stock start script's effective exports in `env` because this runner launches the
frozen binary directly. Root provides the previously verified Rust exports.
Only direct single-process executables are supported by the reused lifecycle
helper. Source, binary, configuration and tools are frozen in each run; the full
conformance log is copied and tied to the binary hash. Missing correctness proof
allows collection of diagnostics but prevents a qualified capacity score.

The app and PostgreSQL share 8 CPU/16 GiB/no swap. A separate owned client
container has an explicit `load_cpus` quota of 4 or 8 CPU and an explicit
`load_memory_bytes` budget of 4 or 8 GiB, with no swap. Defaults remain 4 CPU/4 GiB;
the new complete study declares 8 CPU/8 GiB for both implementations to give
the external clients headroom at 160,000 users and five-minute holds. Docker
memory/swap limits, CPU quota, both inspections and continuous monitoring must match
these same declared budgets. Sampled client CPU utilization divides by the
declared CPU quota. The server budget stays 8 CPU/16 GiB. The client shares
only networking and uses the unchanged native binary. Balanced shards each have at most 20,000 users and their own
loopback destination, with at most eight shards, each using `GOMAXPROCS=1`.
The same phase/users workload identifier is used across cases.

Each implementation gets one fresh full-seed clone and one app launch. Its
database and process remain alive through warmup, probes and holds. Warmup is
60 seconds ramp plus 120 seconds measured at 10,000 users. Probes use 60+60
seconds, double from 10,000 users, then bisect toward a 5% pass/fail interval.
The first probe may be changed through a frozen `search_overrides.start_users`
(for example80,000 after an explicit baseline diagnostic); `warmup_users` stays
10,000 and is independent of that probe starting point.
The ceiling is 160,000 users, with at most 16 probes.
The local search normally rounds probes to two significant digits. During
bisection, if that rounding hits either bound while the gap exceeds 5%, it uses
the strict integer midpoint instead (150,000 PASS/160,000 FAIL probes 155,000).
This local rounding policy is frozen in the plan before execution.
Holds use 60+300 seconds,
starting from the highest passing probe and stepping down 5% after failure,
with at most four holds. Every phase has a 15-second tail. Between phases the
runner waits at least 65 seconds to drain client TIME_WAIT, then waits for target
CPU below 15%, up to 90 extra seconds. Idle timeout is recorded, as in the native
search, rather than silently changing the phase.

A valid SLO failure advances the search. A generator limitation, clock change,
missing witness or infrastructure failure stops that implementation and retains
all its attempted phases. A crash or target OOM stops its session without a
restart. There are no automatic replacements or resumed partial sessions.

The auditor reconstructs native histogram sums, counts, SLO/error results and
search decisions from saved inputs. It checks source/runtime identities, actual
normal UID and NOFILE, fixed durable PostgreSQL settings, target/client cgroups,
full measurement coverage, clock consistency, post-load health and OOM counters.
It reports one row per case with every phase preserved. Only a qualified
five-minute hold produces `capacity_users`. A nearby valid failed upper bound
produces a capacity interval; reaching a ceiling/budget without that bound gives
a held-user lower bound. A passing 60-second probe alone is never a five-minute
capacity score. The native SLO permits fewer than 1% measured errors; exact
measured errors and errors across all recorded seconds are reported separately.

The explicitly frozen `dedicated_client_cgroup_v1` policy changes only the CPU
measurement scope for **local qualification**: it requires the external client
cgroup's measured CPU utilization to remain at most 75%. Native `/proc/stat`
reads the whole shared Linux VM, including app/PostgreSQL work, so its whole-VM
CPU flag is retained separately and may remain above 75%. Every native timing
and active-user condition is independently reproduced from raw shard timelines:
mean wake lag, sampler lateness, active VUs and complete measurement seconds.
Every other native generator reason still rejects the phase. Unknown reasons,
inconsistent raw summaries, missing monitor coverage, client OOM, clock changes
and native SLO failures are not waived. The default `native_whole_vm_v1` policy
continues to reject the native whole-VM CPU flag.

Every phase records `classification_scope`, `local_qualified`, the unchanged
`native_verdict`, `native_qualified = native pass && !native lg_limited`, and
whole-VM CPU flag counts. The public table exposes both qualifications on each
scored hold. A locally qualified hold can remain native LG-limited and is not an
official/native-qualified result. This policy applies to both implementations
and all phases, is frozen before the new data, and never reclassifies history.

`python3 audit/test_capacity.py` runs finite-search boundary tests and tampering
checks against saved native evidence. It starts no server or load generator.
