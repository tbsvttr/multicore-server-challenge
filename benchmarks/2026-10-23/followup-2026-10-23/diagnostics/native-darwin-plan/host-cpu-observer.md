# Independent Darwin whole-host CPU observer

Prepared only; no Mach CPU counter read or measured headroom result has yet been
recorded. This separate tool does not modify the current native10k diagnostic,
the original load generator, host settings, or any existing qualification.

After the active diagnostic finishes and the next protocol is frozen, an example
finite invocation is:

```sh
python3 host-cpu-observer.py --out /private/tmp/host-cpu-new-run.jsonl \
  --samples 241 --interval 1 --max-gap 1.5 --expect-cpus 12
```

The output path must be new.241 snapshots produce240 intervals; the first
snapshot is a baseline, never a since-boot CPU estimate. The output retains all
four unsigned32 tick counters, both host wall/monotonic read brackets, return
code/count, interval deltas, wrapping-state flags and failures. Each interval
computes `100*(user+system+nice)/(user+system+nice+idle)` from deltas. The summary
weights by tick totals, rather than averaging interval percentages.

The count includes **all12 host CPUs**, including the target VM, native client,
Docker proxy and unrelated activity. An eventual predeclared75% whole-host
average gate would be conservative relative to a client-only gate, but is a
different local protocol. It is not an8CPU/8GiB client cgroup, the unchanged
native generator still reports its own CPU as unavailable, and neither the
observer nor a future local comparison establishes an official rank.

Intervals are invalid on failed Mach reads/count, zero ticks, an elapsed gap
above the declared maximum, a read taking over100ms, or wall/monotonic
disagreement over100ms. Counter deltas use unsigned32 modulo arithmetic: one
wrap is handled exactly and reported. A per-state delta at least2^31 is rejected
as ambiguous/reset-like. This assumes no multiple wraps during an accepted
interval of at most10s; normal scheduler tick rates on12 CPUs are far below that
range. A reboot cannot preserve the observer process. The raw values permit
independent replay of this assumption and every percentage.

An error, early interruption or invalid interval makes the summary average and
75% observation null. `qualified_headroom` is always false: another auditor must
prove the snapshots bracket the entire predeclared measurement window, bound
boundary uncertainty, preserve every gap/error, and apply the native timer,
active-user and other validity guards independently. A good CPU average cannot
rescue a generator stall. Do not infer phase-average headroom from a whole-run
average containing warmup/drain; use raw snapshots bracketing that phase.

ABI provenance is the installed Apple macOS27.0 SDK at
`/Library/Developer/CommandLineTools/SDKs/MacOSX27.0.sdk/usr/include/`:

- `mach/host_info.h`: `HOST_CPU_LOAD_INFO=3`, four `natural_t cpu_ticks`, count in
  `integer_t` units.
- `mach/machine.h`: user0/system1/idle2/nice3, `CPU_STATE_MAX=4`.
- `mach/mach_host.h`: `host_statistics(host_t, host_flavor_t, host_info_t,
  mach_msg_type_number_t*)` returning `kern_return_t`.
- `mach/mach_init.h`: `mach_host_self()` returns `mach_port_t`.
- `mach/arm/vm_types.h`, `arm/_types.h`, `mach/message.h` and `mach/port.h`:
  signed32 `integer_t`, unsigned32 `natural_t`, port and message-count ABI.

`host-cpu-observer-provenance.json` records exact header/source hashes and the
pre-execution status. No downloaded dependency, compilation or elevated access
is required.
