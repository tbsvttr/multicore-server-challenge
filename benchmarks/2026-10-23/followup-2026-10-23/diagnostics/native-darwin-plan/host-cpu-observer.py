#!/usr/bin/env python3
"""Independent Darwin whole-host tick deltas; see host-cpu-observer.md. Not a score."""
import argparse, ctypes as C, hashlib, json, math, os, platform, sys, time
from pathlib import Path

STATES = ('user', 'system', 'idle', 'nice')

def snapshot(lib, host):
    ticks, count = (C.c_uint32 * 4)(), C.c_uint32(4)
    w0, m0 = time.time_ns(), time.monotonic_ns()
    result = lib.host_statistics(host, 3, C.cast(ticks, C.POINTER(C.c_int32)), C.byref(count))
    m1, w1 = time.monotonic_ns(), time.time_ns()
    return dict(kind='snapshot', wall_before_ns=w0, wall_after_ns=w1,
                mono_before_ns=m0, mono_after_ns=m1, kern_return=result,
                count=count.value, ticks_u32=dict(zip(STATES, ticks)))

def interval(a, b, max_gap):
    dt = (b['mono_after_ns'] - a['mono_after_ns']) / 1e9
    drift = ((b['wall_after_ns'] - a['wall_after_ns']) / 1e9) - dt
    delta = {k: (b['ticks_u32'][k] - a['ticks_u32'][k]) & 0xffffffff for k in STATES}
    reasons = []
    if not 0 < dt <= max_gap: reasons.append('missing_or_late_interval')
    if abs(drift) > .1: reasons.append('wall_monotonic_disagreement')
    if any(x['kern_return'] != 0 or x['count'] != 4 for x in (a, b)): reasons.append('Mach_read_failed')
    if any(x['mono_after_ns'] - x['mono_before_ns'] > 100000000 for x in (a, b)): reasons.append('slow_read')
    if any(v >= 0x80000000 for v in delta.values()) or not sum(delta.values()): reasons.append('ambiguous_or_zero_tick_delta')
    total, busy = sum(delta.values()), sum(v for k, v in delta.items() if k != 'idle')
    return dict(kind='interval', elapsed_s=dt, wall_minus_mono_delta_s=drift,
                ticks_delta=delta, wrapped_states=[k for k in STATES if b['ticks_u32'][k] < a['ticks_u32'][k]],
                valid=not reasons, reasons=reasons, busy_pct=100*busy/total if not reasons else None)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--samples', type=int, default=241, help='includes initial baseline; at least2')
    p.add_argument('--interval', type=float, default=1)
    p.add_argument('--max-gap', type=float, default=1.5)
    p.add_argument('--expect-cpus', type=int, default=12)
    args = p.parse_args()
    assert platform.system() == 'Darwin' and C.sizeof(C.c_uint32) == 4
    assert args.samples >= 2 and all(math.isfinite(v) for v in (args.interval, args.max_gap))
    assert 0 < args.interval < args.max_gap <= 10 and os.cpu_count() == args.expect_cpus
    lib = C.CDLL('/usr/lib/libSystem.B.dylib')
    lib.mach_host_self.argtypes, lib.mach_host_self.restype = [], C.c_uint32
    lib.host_statistics.argtypes = [C.c_uint32, C.c_int32, C.POINTER(C.c_int32), C.POINTER(C.c_uint32)]
    lib.host_statistics.restype = C.c_int32
    host, rows, error = lib.mach_host_self(), [], None
    with args.out.open('x') as out:
        def emit(row): out.write(json.dumps(row, sort_keys=True) + '\n'); out.flush()
        emit(dict(kind='metadata', schema='darwin_whole_host_cpu_v1', cpus=os.cpu_count(),
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  interval_s=args.interval, max_gap_s=args.max_gap, requested_samples=args.samples,
                  scope='All host CPUs including target VM/proxy/unrelated work; no client-only attribution'))
        try:
            previous = snapshot(lib, host); emit(previous)
            for _ in range(args.samples - 1):
                time.sleep(args.interval)
                current = snapshot(lib, host); emit(current)
                row = interval(previous, current, args.max_gap); rows.append(row); emit(row)
                previous = current
        except (Exception, KeyboardInterrupt) as exc:
            error = repr(exc)
        complete = len(rows) == args.samples - 1 and not error and all(r['valid'] for r in rows)
        total = sum(sum(r['ticks_delta'].values()) for r in rows)
        idle = sum(r['ticks_delta']['idle'] for r in rows)
        mean = 100*(total-idle)/total if complete and total else None
        emit(dict(kind='summary', complete_valid_intervals=complete, error=error, intervals=len(rows),
                  weighted_busy_pct=mean, max_interval_busy_pct=max((r['busy_pct'] for r in rows if r['valid']), default=None),
                  observed_average_at_most75pct=(mean <= 75) if mean is not None else None,
                  qualified_headroom=False, limit='Requires predeclared measurement-window coverage and independent native timing/active-VU guards; this observer alone never qualifies a result'))
    return 0 if complete else 2

if __name__ == '__main__': sys.exit(main())
