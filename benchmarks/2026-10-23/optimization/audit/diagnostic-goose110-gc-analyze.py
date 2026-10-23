#!/usr/bin/env python3
"""Read only completed diagnostic phase evidence; never executes target tools."""
import datetime
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path('/private/tmp/multicore-optimize-20261023')
RUN = ROOT / 'diagnosticgoose110_20261023t164733_2f2b88'
OUT = ROOT / 'audit' / 'diagnostic-goose110-gc'
NUMBER = r'[0-9]+(?:\.[0-9]+)?'
GC = re.compile(
    r'^gc (?P<cycle>\d+) @(?P<elapsed>' + NUMBER + r')s (?P<fraction>\d+)%: '
    r'(?P<sweep>' + NUMBER + r')\+(?P<mark>' + NUMBER + r')\+(?P<term>' + NUMBER + r') ms clock, '
    r'(?P<cpu_sweep>' + NUMBER + r')\+(?P<assist>' + NUMBER + r')/(?P<dedicated>' + NUMBER + r')/(?P<idle>' + NUMBER + r')\+(?P<cpu_term>' + NUMBER + r') ms cpu, '
    r'(?P<heap0>\d+)->(?P<heap1>\d+)->(?P<heap2>\d+) MB, (?P<goal>\d+) MB goal, (?P<stacks>\d+) MB stacks, (?P<globals>\d+) MB globals, (?P<procs>\d+) P(?: \(forced\))?$'
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(events):
    if not events:
        return {'cycles': 0}
    maximum = lambda key: max(events, key=lambda e: e[key])
    return {
        'cycles': len(events),
        'max_individual_stw_phase_ms': max(max(e['sweep_termination_ms'], e['mark_termination_ms']) for e in events),
        'max_combined_stw_ms_per_cycle': maximum('stw_sum_ms')['stw_sum_ms'],
        'max_stw_cycle': maximum('stw_sum_ms')['cycle'],
        'max_concurrent_mark_wall_ms': maximum('concurrent_mark_ms')['concurrent_mark_ms'],
        'max_concurrent_mark_cycle': maximum('concurrent_mark_ms')['cycle'],
        'sum_stw_clock_ms': sum(e['stw_sum_ms'] for e in events),
        'sum_concurrent_mark_wall_ms': sum(e['concurrent_mark_ms'] for e in events),
        'sum_gc_cpu_ms_printed': sum(e['cpu_total_ms'] for e in events),
        'sum_mark_assist_cpu_ms': sum(e['assist_cpu_ms'] for e in events),
        'max_heap_before_mb': max(e['heap_before_mb'] for e in events),
        'max_heap_after_mark_mb': max(e['heap_after_mark_mb'] for e in events),
        'max_heap_live_mb': max(e['heap_live_mb'] for e in events),
        'max_heap_goal_mb': max(e['heap_goal_mb'] for e in events),
        'max_stack_scan_mb': max(e['stacks_scan_mb'] for e in events),
        'last_runtime_gc_fraction_percent': events[-1]['runtime_gc_fraction_percent'],
        'cycles_with_stw_over_1000ms': [e['cycle'] for e in events if max(e['sweep_termination_ms'], e['mark_termination_ms']) >= 1000],
        'cycles_with_concurrent_mark_over_1000ms': [e['cycle'] for e in events if e['concurrent_mark_ms'] >= 1000],
    }


def parse_box(phase, index):
    path = phase / f'box{index}.log'
    boxpath = phase / f'box{index}.json'
    box = json.loads(boxpath.read_text()) if boxpath.exists() else None
    if box is not None:
        meta = box['meta']
    else:
        commands = json.loads((phase / 'load-commands.json').read_text())
        args = commands[index]
        arg = lambda key: args[args.index(key) + 1]
        start_ms = int(arg('-start-at'))
        ramp, measure, tail = [float(arg(key).removesuffix('s')) for key in ['-ramp', '-measure', '-tail']]
        meta = {'start_at_ms': start_ms, 'ramp_s': ramp, 'measure_s': measure, 'tail_s': tail, 'window_start_ms': start_ms + ramp * 1000, 'window_end_ms': start_ms + (ramp + measure) * 1000, 'box_index': index, 'inferred_from_frozen_command_because_box_json_missing': True}
    events, unmatched = [], []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.startswith('gc '):
            continue
        m = GC.fullmatch(line)
        if not m:
            unmatched.append({'line': number, 'text': line})
            continue
        g = m.groupdict()
        f = lambda key: float(g[key])
        event = {
            'line': number, 'cycle': int(g['cycle']), 'runtime_start_s': f('elapsed'),
            'runtime_gc_fraction_percent': int(g['fraction']),
            'sweep_termination_ms': f('sweep'), 'concurrent_mark_ms': f('mark'),
            'mark_termination_ms': f('term'), 'stw_sum_ms': f('sweep') + f('term'),
            'stw_sweep_cpu_ms': f('cpu_sweep'), 'assist_cpu_ms': f('assist'),
            'dedicated_mark_cpu_ms': f('dedicated'), 'idle_mark_cpu_ms': f('idle'),
            'stw_mark_cpu_ms': f('cpu_term'),
            'cpu_total_ms': sum(f(k) for k in ['cpu_sweep', 'assist', 'dedicated', 'idle', 'cpu_term']),
            'heap_before_mb': int(g['heap0']), 'heap_after_mark_mb': int(g['heap1']),
            'heap_live_mb': int(g['heap2']), 'heap_goal_mb': int(g['goal']),
            'stacks_scan_mb': int(g['stacks']), 'globals_scan_mb': int(g['globals']),
            'gomaxprocs': int(g['procs']),
        }
        end = f('elapsed') + sum(f(k) for k in ['sweep', 'mark', 'term']) / 1000
        event['runtime_end_s'] = end
        # start_ms is assigned now+5s before Popen; the native warning, if late,
        # is emitted before the run line. No exact process runtime-init clock
        # anchor was recorded. Preserve the full intended-lead uncertainty.
        event['phase_start_time_range_s'] = [f('elapsed') - 5, f('elapsed')]
        event['phase_end_time_range_s'] = [end - 5, end]
        start = meta['ramp_s']
        stop = start + meta['measure_s']
        event['possibly_in_measurement'] = event['phase_end_time_range_s'][1] >= start and event['phase_start_time_range_s'][0] <= stop
        event['definitely_in_measurement'] = event['phase_start_time_range_s'][0] >= start and event['phase_end_time_range_s'][1] <= stop
        events.append(event)
    timeline = box['timeline'] if box is not None else []
    metric_keys = ['t', 'completed', 'errors', 'active_vus', 'tick_lag_ms', 'wake_lag_mean_ms', 'wake_lag_max_ms', 'p50_ms', 'p95_ms', 'p99_ms', 'proc_cpu_pct', 'rss_mb', 'goroutines']
    slim = lambda r: {key: r.get(key) for key in metric_keys}
    late = sorted(timeline, key=lambda row: row.get('tick_lag_ms', 0), reverse=True)[:12]
    inter_gc_quiet = []
    for before, after in zip(events, events[1:]):
        # Across every allowed runtime-init anchor, this open phase interval
        # falls after the earlier complete collection and before the next.
        left, right = before['runtime_end_s'], after['runtime_start_s'] - 5
        if right > left:
            inter_gc_quiet.append({'phase_interval_s': [left, right], 'after_cycle': before['cycle'], 'before_cycle': after['cycle']})
    actual_sample_gaps = []
    for before, after in zip(timeline, timeline[1:]):
        # A final allDone sample has no tick-lag anchor; exclude that case.
        if after.get('active_vus') == 0 and after.get('tick_lag_ms') == 0:
            continue
        left = before['t'] + 1 + before.get('tick_lag_ms', 0) / 1000
        right = after['t'] + 1 + after.get('tick_lag_ms', 0) / 1000
        if right - left <= 1.1:
            continue
        quiet = next((q for q in inter_gc_quiet if q['phase_interval_s'][0] < left and q['phase_interval_s'][1] > right), None)
        actual_sample_gaps.append({'previous_nominal_t': before['t'], 'next_nominal_t': after['t'], 'previous_actual_phase_s': left, 'next_actual_phase_s': right, 'elapsed_s': right - left, 'next_tick_lag_ms': after.get('tick_lag_ms'), 'wholly_inside_definite_between_collections_gap': quiet})
    actual_sample_gaps.sort(key=lambda r: r['elapsed_s'], reverse=True)
    log_text = path.read_text()
    anchor_ok = 'run: warning: start-at is ' not in log_text
    return {
        'box': index, 'meta': meta, 'native_box_summary': box['box'] if box is not None else None,
        'native_result_missing': box is None,
        'source': {'log': str(path), 'log_sha256': digest(path), 'box_json': str(boxpath), 'box_json_sha256': digest(boxpath) if box is not None else None},
        'alignment': {
            'exact_runtime_init_anchor_recorded': False,
            'native_late_start_warning_absent': anchor_ok,
            'runtime_init_relative_to_phase_s_range': [-5, 0] if anchor_ok else None,
            'range_basis': 'Frozen controller assigns start_at=now+5000ms before Popen; no native late-start warning. Per-process launch/runtime-init timestamp was not saved. Do not treat @ as phase time.',
        },
        'all_process_gc': summarize(events),
        'definitely_measurement_gc': summarize([e for e in events if e['definitely_in_measurement']]),
        'possibly_measurement_gc': summarize([e for e in events if e['possibly_in_measurement']]),
        'unparsed_gc_lines': unmatched,
        'definite_between_completed_collection_phase_intervals': inter_gc_quiet,
        'longest_actual_sampler_intervals': actual_sample_gaps[:12],
        'top_sampler_lag_seconds': [slim(r) for r in late],
        'first_timeline_error': next((slim(r) for r in timeline if r.get('errors', 0)), None),
        'last_timeline_sample': slim(timeline[-1]) if timeline else None,
        'gc_events': events,
    }


def main():
    phases, pending = [], []
    for phase in sorted((RUN / 'cases' / 'goose32' / 'phases').iterdir()):
        if not phase.is_dir():
            continue
        assessment_path = phase / 'assessment.json'
        if not assessment_path.exists():
            pending.append(phase.name)
            continue
        assessment = json.loads(assessment_path.read_text())
        phase_config = json.loads((phase / 'phase.json').read_text())
        boxes = [parse_box(phase, shard['box_index']) for shard in phase_config['shards']]
        phases.append({
            'id': phase.name, 'users': phase_config['users'],
            'assessment_path': str(assessment_path), 'assessment_sha256': digest(assessment_path),
            'classification': assessment['classification'], 'phase_error': phase_config.get('error'),
            'all_classifications': assessment.get('all_classifications'),
            'native_verdict': assessment.get('native_verdict'),
            'overall': assessment.get('overall'), 'diagnostic_only': assessment.get('diagnostic_only'),
            'capacity_score': assessment.get('capacity_score'), 'boxes': boxes,
        })
    result = {
        'schema': 'diagnostic_client_gc_analysis_v1',
        'generated_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'run': str(RUN), 'scope': 'Diagnostic client/runtime evidence only; no performance, capacity, or rank claim.',
        'completed_phases_analyzed': [p['id'] for p in phases], 'pending_phases_not_read': pending,
        'evidence_rules': [
            'Only box logs whose phase already has assessment.json are read.',
            'GC first+last clock values are separate stop-the-world sweep/mark termination phases; the middle clock value is concurrent marking, not a full stop-the-world pause.',
            'Printed CPU values are cumulative worker/assist CPU time per GC cycle; concurrent-mark wall duration can include descheduling and mutator work.',
            'No exact runtime-init wall anchor was saved. GC @ times are process-relative and retain the controller\'s 0..5-second phase alignment uncertainty.',
            'Sampler histograms can be shifted relative to nominal counter buckets after delayed sampling; timeline quantiles are not an independent server service-time trace.',
            'Absence of long completed STW traces alone does not exclude uncompleted runtime work, host descheduling, allocation assists, or server/backlog effects.',
        ],
        'format_reference': {'path': '/opt/homebrew/opt/go/libexec/src/runtime/mgc.go', 'version': 'go1.27.2', 'lines': [1588,1633], 'exact_native_runtime_version_not_inferred_from_this_local_reference': True},
        'phases': phases,
    }
    OUT.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = ['# Client GC diagnostic', '', result['scope'], '', 'Only completed phase logs were read. GC `@` is runtime-relative: the saved launch protocol bounds its phase-time offset to −5..0 seconds, but records no exact runtime-init clock anchor.', '', 'The first and last printed clock values are STW termination phases. The middle value is concurrent marking; a seconds-long middle value does not mean the application was stopped for seconds.', '']
    for p in phases:
        lines += [f"## {p['id']}", '', f"Assessment: `{p['classification']}`; other classifications: {', '.join(p['all_classifications'] or [])}. This remains diagnostic evidence.", '', '| Shard | Cycles | Largest individual STW, ms | Largest combined STW/cycle, ms | Longest concurrent mark, ms | Max live/goal heap, MiB | Max sampler lag, ms |', '|---:|---:|---:|---:|---:|---:|---:|']
        for b in p['boxes']:
            s = b['all_process_gc']
            lag = b['top_sampler_lag_seconds'][0]['tick_lag_ms'] if b['top_sampler_lag_seconds'] else None
            lag_display = f'{lag:g}' if lag is not None else 'unavailable (missing result)'
            lines.append(f"| {b['box']} | {s['cycles']} | {s.get('max_individual_stw_phase_ms', 0):g} | {s.get('max_combined_stw_ms_per_cycle', 0):g} | {s.get('max_concurrent_mark_wall_ms', 0):g} | {s.get('max_heap_live_mb', 0)}/{s.get('max_heap_goal_mb', 0)} | {lag_display} |")
        longstw = sum(len(b['all_process_gc'].get('cycles_with_stw_over_1000ms', [])) for b in p['boxes'])
        lines += ['', f"Completed GC traces with an individual STW phase ≥1 second: **{longstw}**.", '']
        if p['phase_error']:
            lines += ['Phase ended with: `' + p['phase_error'] + '`. Missing native JSON results prevent complete timeline and end-to-end accounting; GC logs are partial evidence.', '']
        for b in p['boxes']:
            for gap in b['longest_actual_sampler_intervals'][:3]:
                quiet = gap['wholly_inside_definite_between_collections_gap']
                if quiet is not None:
                    left, right = quiet['phase_interval_s']
                    lines += [f"Shard {b['box']} has a saved sampler gap from phase {gap['previous_actual_phase_s']:.6f} to {gap['next_actual_phase_s']:.6f} seconds ({gap['elapsed_s']:.6f} seconds elapsed). It lies wholly between completed GC cycles {quiet['after_cycle']} and {quiet['before_cycle']}, whose conservative no-collection interval is phase {left:.6f}..{right:.6f} seconds after retaining the full 5-second runtime-origin uncertainty. Thus an overlapping recorded STW/concurrent collection does not explain that gap. This does not exclude background sweep/allocation work or host descheduling.", '']
    if pending:
        lines += ['Pending phases were not read: ' + ', '.join(pending) + '.', '']
    lines += ['A completed concurrent-mark interval may overlap delayed sampling within the stated alignment range; that establishes timing compatibility, not causation. Neither GC nor server service time should be named as the cause without the corresponding trace and PostgreSQL evidence.', '']
    OUT.with_suffix('.md').write_text('\n'.join(lines))
    print(json.dumps({'completed': result['completed_phases_analyzed'], 'pending': pending, 'output_json': str(OUT.with_suffix('.json')), 'output_md': str(OUT.with_suffix('.md'))}))


if __name__ == '__main__':
    main()
