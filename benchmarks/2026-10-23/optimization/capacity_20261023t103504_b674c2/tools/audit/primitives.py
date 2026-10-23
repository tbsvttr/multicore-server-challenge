"""Pure saved-evidence primitives copied from the reviewed2026-10-22 audit. No I/O beyond files."""

import base64, bisect, collections, hashlib, json, math, re, struct, zlib

from pathlib import Path

GiB=1024**3

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default

def jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []

def check(checks, label, condition, detail=None):
    row = {'check': label, 'pass': bool(condition)}
    if not condition or detail is not None:
        row['detail'] = detail
    checks.append(row)

def events_dict(text):
    return {k: int(v) for k, v in (line.split() for line in text.splitlines())}

def setting_map(snapshot):
    return {s['name']: (s['setting'], s['unit'], s['source']) for s in snapshot['pg_settings']}

def inspect_budget(obj, cpus, memory):
    h = obj['HostConfig']
    return (h['NanoCpus'] == cpus * 10 ** 9 and h['Memory'] == memory
            and h['MemorySwap'] == memory and h['CpusetCpus'] == '' and h.get('CpusetMems', '') == '')

def monitor(path, meta, cpus, memory):
    rows = jsonl(path)
    checks, warnings = [], []
    start, end = meta['window_start_ms'] * 10 ** 6, meta['window_end_ms'] * 10 ** 6
    check(checks, 'monitor_has_samples', len(rows) >= 2)
    if len(rows) < 2:
        return {'checks': checks, 'warnings': warnings, 'eligible': False}
    walls = [r['wall_ns'] for r in rows]
    check(checks, 'strict_wall_and_monotonic_order', all(
        b['wall_ns'] > a['wall_ns'] and b['monotonic_ns'] > a['monotonic_ns'] for a, b in zip(rows, rows[1:])))
    check(checks, 'full_measurement_window_bracketed', walls[0] <= start and walls[-1] >= end,
          {'first_ms': walls[0] / 1e6, 'start_ms': start / 1e6, 'last_ms': walls[-1] / 1e6, 'end_ms': end / 1e6})
    lo, hi = max(0, bisect.bisect_right(walls, start) - 1), min(len(rows), bisect.bisect_left(walls, end) + 1)
    selected = rows[lo:hi]
    gaps = [(b['monotonic_ns'] - a['monotonic_ns']) / 1e9 for a, b in zip(selected, selected[1:])]
    max_gap = max(gaps, default=None)
    check(checks, 'max_sample_gap_at_most_3s', max_gap is not None and max_gap <= 3, max_gap)
    check(checks, 'cgroup_budget_continuous', all(
        r.get('cpu.max') == f'{cpus * 100000} 100000'
        and int(r.get('memory.max') or -1) == memory and int(r.get('memory.swap.max') or -1) == 0
        and int(r.get('memory.swap.current') or -1) == 0
        and int(r.get('memory.current') or memory + 1) <= memory for r in selected))
    check(checks, 'total_cpu_counter_nondecreasing', all(
        b['cpu']['usage_usec'] >= a['cpu']['usage_usec'] for a, b in zip(selected, selected[1:])))
    first_events, last_events = events_dict(selected[0]['memory.events']), events_dict(selected[-1]['memory.events'])
    oom_delta = {k: last_events.get(k, 0) - first_events.get(k, 0) for k in ['oom', 'oom_kill', 'oom_group_kill']}
    check(checks, 'no_measurement_oom', all(v == 0 for v in oom_delta.values()), oom_delta)
    clock_offsets = [(r['wall_ns'] - r['monotonic_ns']) / 1e9 for r in selected]
    drift = max(clock_offsets) - min(clock_offsets)
    check(checks, 'wall_to_monotonic_drift_below_100ms', drift < .1, drift)

    def at(t, getter):
        k = max(0, min(len(rows) - 2, bisect.bisect_right(walls, t) - 1))
        a, b = rows[k], rows[k + 1]
        fraction = (t - a['wall_ns']) / (b['wall_ns'] - a['wall_ns'])
        return getter(a) + fraction * (getter(b) - getter(a))

    seconds = (end - start) / 1e9
    total_cpu = at(end, lambda r: r['cpu']['usage_usec'] / 1e6) - at(start, lambda r: r['cpu']['usage_usec'] / 1e6)
    interval_utilization = [(b['cpu']['usage_usec'] - a['cpu']['usage_usec']) / 1e6
                            / ((b['monotonic_ns'] - a['monotonic_ns']) / 1e9) / cpus * 100
                            for a, b in zip(selected, selected[1:])]
    result = {'checks': checks, 'warnings': warnings, 'eligible': all(c['pass'] for c in checks),
              'samples': len(selected), 'max_gap_s': max_gap, 'window_s': seconds,
              'cgroup_cpu_seconds_estimate': total_cpu, 'cgroup_quota_utilization_pct': total_cpu / seconds / cpus * 100,
              'max_sample_interval_quota_utilization_pct': max(interval_utilization, default=None),
              'memory_peak_sampled_bytes': max(int(r['memory.current']) for r in selected),
              'memory_counter_peak_bytes': max(int(r['memory.peak']) for r in selected),
              'swap_peak_sampled_bytes': max(int(r['memory.swap.current']) for r in selected), 'oom_delta': oom_delta}
    for kind in ['app', 'pg']:
        stable_pids = len({tuple(sorted(r[kind]['pids'])) for r in selected}) == 1
        monotone = all(b[kind]['cpu_s'] >= a[kind]['cpu_s'] for a, b in zip(selected, selected[1:]))
        valid_component = stable_pids and monotone
        value = at(end, lambda r: r[kind]['cpu_s']) - at(start, lambda r: r[kind]['cpu_s']) if valid_component else None
        result[kind + '_cpu_seconds_estimate'] = value
        result[kind + '_counter_valid'] = valid_component
        result[kind + '_pids_stable'] = stable_pids
        result[kind + '_process_count_max'] = max(len(r[kind]['pids']) for r in selected)
        result[kind + '_whole_target_cpu_pct'] = value / seconds / 8 * 100 if value is not None else None
        if not valid_component:
            warnings.append(f'{kind}: live-PID CPU sum changed population or decreased; component CPU withheld')
    return result

def histogram(text):
    """Decode saved HdrHistogramV2 bins to verify exact sums, not quantile means."""
    if not text:
        return None, collections.Counter()
    encoded = base64.b64decode(text, validate=True)
    cookie, length = struct.unpack('>II', encoded[:8])
    if cookie != 0x1c849314 or len(encoded) != length + 8:
        raise ValueError('unexpected HdrHistogram compressed header')
    data = zlib.decompress(encoded[8:])
    header = struct.unpack('>iiiiqqd', data[:40])
    cookie, length, normalization, significant, low, high, ratio = header
    if cookie != 0x1c849313 or normalization != 0 or length != len(data) - 40:
        raise ValueError('unexpected HdrHistogramV2 configuration')
    bins, index, at = collections.Counter(), 0, 40
    while at < len(data):
        value = shift = 0
        while True:
            byte = data[at]; at += 1
            value |= (byte & 127) << shift
            if byte < 128: break
            shift += 7
            if shift > 63: raise ValueError('invalid histogram varint')
        signed = (value >> 1) ^ -(value & 1)
        if signed < 0: index += -signed
        else:
            if signed: bins[index] += signed
            index += 1
    return (significant, low, high, ratio), bins

def histogram_quantile_ms(config, bins, quantile):
    if not bins: return 0
    significant, low, _, ratio = config
    if ratio != 1: raise ValueError('unexpected histogram conversion ratio')
    unit = low.bit_length() - 1
    half_bits = (2 * 10 ** significant - 1).bit_length() - 1
    target, seen = max(1, int(sum(bins.values()) * quantile / 100 + .5)), 0
    for index, count in sorted(bins.items()):
        seen += count
        if seen >= target:
            bucket = (index >> half_bits) - 1
            sub = (index & ((1 << half_bits) - 1)) + (1 << half_bits)
            if bucket < 0: sub -= 1 << half_bits; bucket = 0
            return ((sub + 1) * (1 << (bucket + unit)) - 1) / 1000
    return 0

def exact_merge(raws, merged):
    checks = []
    total, statuses, errors, count, endpoints, configurations = collections.Counter(), collections.Counter(), collections.Counter(), 0, {}, set()
    for raw in raws:
        for name, endpoint in raw['endpoints'].items():
            config, bins = histogram(endpoint['hist'])
            configurations.add(config)
            total.update(bins)
            count += endpoint['count']
            statuses.update(endpoint.get('statuses', {}))
            errors.update(endpoint.get('errors', {}))
            endpoints.setdefault(name, collections.Counter()).update(bins)
            check(checks, 'raw_hist_count:' + str(raw['meta']['box_index']) + ':' + name, sum(bins.values()) == endpoint['count'])
    config, bins = histogram(merged.get('hist', ''))
    check(checks, 'all_histogram_configurations_match', not configurations or configurations == {config})
    check(checks, 'merged_histogram_equals_exact_bin_sum', bins == total)
    for name, quantile in [('p50_ms', 50), ('p95_ms', 95), ('p99_ms', 99), ('max_ms', 100)]:
        check(checks, 'merged_quantile_from_exact_histogram:' + name,
              math.isclose(merged['overall'][name], histogram_quantile_ms(config, bins, quantile), rel_tol=1e-12))
    check(checks, 'merged_count_equals_raw_counts', merged['overall']['count'] == count == sum(total.values()))
    check(checks, 'merged_statuses_equal_raw_counts', merged['overall'].get('statuses', {}) == dict(statuses))
    check(checks, 'merged_errors_equal_raw_counts', merged['overall']['errors'] == sum(errors.values())
          and merged['overall'].get('error_classes', {}) == dict(errors))
    merged_endpoints = {endpoint['name']: endpoint for endpoint in (merged.get('endpoints') or [])}
    check(checks, 'all_endpoints_retained', set(endpoints) == set(merged_endpoints))
    for name, counts in endpoints.items():
        if name in merged_endpoints:
            check(checks, 'endpoint_count:' + name, merged_endpoints[name]['count'] == sum(counts.values()))
    return checks

def native_verdict(merged, raws):
    overall = merged['overall']
    return {'pass': overall['count'] > 0 and overall['p95_ms'] < 500 and overall['p99_ms'] < 1000 and overall['error_rate'] < .01,
            'lg_limited': any(raw['box'].get('fell_behind', False) or (raw['box'].get('cpu_avg_measure_pct') or 0) > 75 for raw in raws)}

def generator_details(raws, merged):
    """Reproduce native run.go boxStats and merge.go LG reasons from timelines."""
    checks, reasons, cpu_flags, timing_failed = [], [], [], []
    for raw in raws:
        meta, box = raw['meta'], raw['box']
        index, lo = meta['box_index'], meta['ramp_s']
        hi = lo + meta['measure_s']
        rows = [s for s in raw['timeline'] if lo <= s['t'] < hi]
        n = len(rows)
        active = next((s['active_vus'] for s in rows if s['t'] == lo), 0)
        slow = sum(s['wake_lag_mean_ms'] > 50 for s in rows)
        tick = max((s['tick_lag_ms'] for s in rows), default=0)
        expected = []
        if slow > max(2, n // 20):
            expected.append(f'{slow} of {n} seconds had mean timer wake-up lag > 50 ms')
        if tick > 500:
            expected.append(f'sampler tick {tick:.0f} ms late')
        if n and active < .99 * meta['users']:
            expected.append(f"only {active} of {meta['users']} users active at window start")
        if not n:
            expected.append('no samples in the measure window')
        cpu = [s['cpu_pct'] for s in rows if s.get('cpu_pct') is not None]
        avg = sum(cpu) / len(cpu) if cpu else None
        maximum = max(cpu) if cpu else None
        def same(a, b):
            return a is b if a is None or b is None else math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
        check(checks, f'shard{index}:native_box_CPU_reproduced_from_timeline', same(box.get('cpu_avg_measure_pct'), avg)
              and same(box.get('cpu_max_measure_pct'), maximum))
        check(checks, f'shard{index}:native_timing_summary_reproduced', box.get('fell_behind') is bool(expected)
              and (box.get('fell_behind_reasons') or []) == expected and box.get('active_vus_at_window_start') == active)
        check(checks, f'shard{index}:complete_measurement_timeline', [s['t'] for s in rows] == list(range(lo, hi)))
        if expected or [s['t'] for s in rows] != list(range(lo, hi)):
            timing_failed.append(index)
        if avg is not None and avg > 75:
            cpu_flags.append(index)
            reasons.append(f'box {index} CPU {avg:.0f}% > 75%')
        if expected:
            reasons.append(f"box {index} fell behind: {'; '.join(expected)}")
        saved = next((b for b in merged['boxes'] if b['box_index'] == index), {})
        check(checks, f'shard{index}:merged_generator_summary_matches_raw',
              all(saved.get(k) == box.get(k) for k in ['cpu_avg_measure_pct', 'cpu_max_measure_pct', 'fell_behind'])
              and (saved.get('fell_behind_reasons') or []) == (box.get('fell_behind_reasons') or []))
    check(checks, 'native_generator_reasons_reproduced_exactly', (merged['verdict'].get('lg_reasons') or []) == reasons)
    return {'checks': checks, 'whole_vm_CPU_flagged_shards': cpu_flags,
            'timing_failed_shards': timing_failed, 'expected_native_lg_reasons': reasons}

def actual_process_checks(witness, app, label):
    """Reparse raw kernel records independently of helper validity booleans."""
    checks = []
    uid = app.get('app_uid')
    check(checks, label + ':normal_expected_uid', isinstance(uid, int) and uid > 0)
    if not isinstance(witness, dict):
        check(checks, label + ':actual_process_witness_present', False)
        return checks
    processes = witness.get('processes', [])
    check(checks, label + ':exactly_one_expected_process', len(processes) == 1 and witness.get('expected_uid') == uid)
    if len(processes) != 1: return checks
    proc = processes[0]
    status, limits = proc.get('proc_status', ''), proc.get('proc_limits', '')
    raw_uid = re.search(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$', status, re.M)
    raw_pid = re.search(r'^Pid:\s+(\d+)\s*$', status, re.M)
    raw_limit = re.search(r'^Max open files\s+(\S+)\s+(\S+)', limits, re.M)
    parsed_uids = [int(x) for x in raw_uid.groups()] if raw_uid else []
    parsed_limits = [int(x) if x.isdigit() else x for x in raw_limit.groups()] if raw_limit else []
    enough = lambda value: value == 'unlimited' or isinstance(value, int) and value >= 200000
    check(checks, label + ':raw_all_four_uids_match_normal_user', parsed_uids == [uid] * 4
          and proc.get('uids') == parsed_uids and proc.get('uid') == uid)
    check(checks, label + ':raw_actual_pid_matches', raw_pid is not None and int(raw_pid[1]) == proc.get('pid') == app.get('actual_app_pid'))
    check(checks, label + ':actual_process_identity_stable', proc.get('pid') == app.get('actual_app_pid')
          and proc.get('start_ticks') == app.get('actual_app_start_ticks') and proc.get('pgid') == app.get('pgid')
          and proc.get('exe') == app.get('frozen_binary'))
    check(checks, label + ':raw_soft_hard_nofile_at_least_200000', len(parsed_limits) == 2 and all(enough(v) for v in parsed_limits)
          and parsed_limits == [proc.get('nofile_soft'), proc.get('nofile_hard')], parsed_limits)
    check(checks, label + ':helper_validity_agrees_with_raw', witness.get('valid') is True)
    return checks
