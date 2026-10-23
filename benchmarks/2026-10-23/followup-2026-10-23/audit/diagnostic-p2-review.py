#!/usr/bin/env python3
"""Analyze completed P2 files only; never calls Docker, SQL, a build, or load."""
import collections
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path('/private/tmp/multicore-optimize-20261023')
RUN = ROOT / 'diagnosticgoose110p2_20261023t181051_2b1bad'
OUT = ROOT / 'audit' / 'diagnostic-p2-review'
EXPECTED_BINARY = '7a7c31fbaedbb9687f048158623b3c311ea5f240ecc4bfcff985b718bd2afc21'
EXPECTED_PLAN = '3216bf9369eee3d245aa25234c9346fcfa9df8cdec951bafb62aaf6f56029899'
inputs = {}


def raw(path):
    content = path.read_bytes()
    inputs[str(path.resolve().relative_to(ROOT.resolve()))] = {
        'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
    return content


def read(path):
    return json.loads(raw(path))


def rows(path):
    return [json.loads(line) for line in raw(path).splitlines()]


def quota(text):
    numerator, denominator = map(int, text.split())
    assert numerator > 0 and denominator > 0
    return numerator / denominator


def cpu_at(monitors, wall_ns):
    for left, right in zip(monitors, monitors[1:]):
        if left['wall_ns'] <= wall_ns <= right['wall_ns']:
            fraction = (wall_ns - left['wall_ns']) / (right['wall_ns'] - left['wall_ns'])
            return left['cpu']['usage_usec'] + fraction * (
                right['cpu']['usage_usec'] - left['cpu']['usage_usec'])
    raise AssertionError('CPU window not bracketed')


def summarize_pg(path, start_ms, stop_ms):
    samples = rows(path)
    okay = [row for row in samples if row.get('ok')]
    counters = collections.Counter()
    families = collections.Counter()
    blocks, ages = [], []
    for row in okay:
        pg = row['postgres']
        observation = pg.get('blocking_observation', {})
        if observation.get('blocker_pid_count'):
            blocks.append({'wall_ns': row['wall_ns'], **observation})
        for activity in pg['activity']:
            counters[(activity.get('state'), activity.get('wait_event_type'),
                      activity.get('wait_event'))] += 1
            families[activity['family']] += 1
            if activity['state'] == 'active' and activity.get('query_age_s') is not None:
                ages.append(activity['query_age_s'])
    measured = [row for row in okay if start_ms <= row['wall_ns'] / 1e6 < stop_ms]
    measured_activity = [a for row in measured for a in row['postgres']['activity']]
    return {
        'samples': len(samples), 'successful_samples': len(okay),
        'errors': [{'sample': row.get('sample'), 'error': row.get('error')}
                   for row in samples if not row.get('ok')],
        'max_successful_observer_duration_s': max(
            (row['finished_monotonic_ns'] - row['monotonic_ns']) / 1e9 for row in okay),
        'all_phase_backend_observations': sum(counters.values()),
        'all_phase_wait_observation_counts': [
            {'state': key[0], 'wait_event_type': key[1], 'wait_event': key[2], 'count': value}
            for key, value in counters.most_common()],
        'all_phase_family_observation_counts': dict(families),
        'blocking_samples': len(blocks), 'blocking_observations': blocks,
        'max_sampled_active_query_age_s': max(ages) if ages else None,
        'measurement_samples': len(measured),
        'measurement_backend_observations': len(measured_activity),
        'measurement_idle_observations': sum(a['state'] == 'idle' for a in measured_activity),
        'measurement_active_observations': sum(a['state'] == 'active' for a in measured_activity),
        'measurement_WAL_wait_observations': sum(
            a.get('wait_event') in ('WalSync', 'WALWrite', 'WalWrite') for a in measured_activity),
        'interpretation': 'Sample counts are observations, not independent requests or exact wait durations; unsampled intervals and failed observer samples remain unknown.'}


def main():
    raw(Path(__file__))
    parser_path = ROOT / 'audit/diagnostic-goose110-gc-analyze.py'
    raw(parser_path)
    spec = importlib.util.spec_from_file_location('saved_gc_parser', parser_path)
    gc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gc)
    checks = []

    def check(name, passed, **detail):
        checks.append({'check': name, 'pass': bool(passed), **detail})

    plan = read(RUN / 'plan.json')
    check('executed_plan_exact_expected_SHA', inputs[str((RUN / 'plan.json').resolve().relative_to(ROOT.resolve()))]['sha256'] == EXPECTED_PLAN)
    check('fixed_sequence_no_capacity_or_holds', plan.get('capacity_search_disabled') is True and plan.get('holds_disabled') is True)
    metadata = read(RUN / 'cases/goose32/frozen/metadata.json')
    binary = RUN / 'cases/goose32/frozen/conduit'
    if not binary.exists():
        binary = ROOT / metadata['frozen_binary'] if not Path(metadata['frozen_binary']).is_absolute() else Path(metadata['frozen_binary'])
        # Container paths are mapped explicitly to the saved host comparison path.
        if not binary.exists() and str(binary).startswith('/comparison/'):
            binary = Path('/private/tmp/multicore-comparison-20261023') / str(binary).removeprefix('/comparison/')
    binary_sha = hashlib.sha256(raw(binary)).hexdigest()
    check('unchanged_A_binary_not_B', binary_sha == EXPECTED_BINARY == metadata['binary_sha256'])
    phases = []
    all_gc = []
    for directory in sorted((RUN / 'cases/goose32/phases').iterdir()):
        assessment = read(directory / 'assessment.json')
        phase = read(directory / 'phase.json')
        boxes = []
        for shard in phase['shards']:
            index = shard['box_index']
            box = read(directory / f'box{index}.json')
            raw(directory / f'box{index}.log')
            parsed = gc.parse_box(directory, index)
            all_gc.extend(parsed['gc_events'])
            boxes.append({
                'index': index, 'users': box['meta']['users'],
                'GOMAXPROCS': box['meta']['gomaxprocs'],
                'native_summary': box['box'],
                'GC': parsed['all_process_gc'],
                'unparsed_GC_lines': parsed['unparsed_gc_lines'],
                'alignment': parsed['alignment'],
                'longest_sampler_intervals': parsed['longest_actual_sampler_intervals'],
                'first_timeline_error': parsed['first_timeline_error']})
        first_box = read(directory / f"box{phase['shards'][0]['box_index']}.json")
        window_start_ns = round(first_box['meta']['window_start_ms'] * 1e6)
        window_end_ns = round(first_box['meta']['window_end_ms'] * 1e6)
        pg = summarize_pg(directory / 'pg-samples.jsonl',
                          first_box['meta']['window_start_ms'], first_box['meta']['window_end_ms'])
        budget = {}
        for kind, memory in [('target', 16 * 1024**3), ('load', 8 * 1024**3)]:
            monitors = rows(directory / f'{kind}-monitor.jsonl')
            offsets = [row['wall_ns'] - row['monotonic_ns'] for row in monitors]
            drift = (max(offsets) - min(offsets)) / 1e9
            recorded = next(x['detail'] for x in assessment['checks']
                            if x['check'] == kind + ':entire_phase_clock_drift_under100ms')
            check(f'{directory.name}:{kind}:guest_clock_span_reproduced', abs(recorded - drift) < 1e-6)
            cpu_seconds = (cpu_at(monitors, window_end_ns) - cpu_at(monitors, window_start_ns)) / 1e6
            check(f'{directory.name}:{kind}:cgroup_CPU_integral_reproduced',
                  abs(cpu_seconds - assessment[kind + '_monitor']['cgroup_cpu_seconds_estimate']) < 1e-3)
            settings = sorted({row['cpu.max'] for row in monitors})
            valid = all(quota(row['cpu.max']) == 8 and int(row['memory.max']) == memory
                        and int(row['memory.swap.max']) == 0 for row in monitors)
            check(f'{directory.name}:{kind}:numeric_8CPU_memory_noSwap', valid)
            budget[kind] = {'raw_cpu_max_values': settings, 'all_numeric_CPU_ratios': sorted({quota(x) for x in settings}),
                            'all_memory_max': sorted({row['memory.max'] for row in monitors}),
                            'all_swap_max': sorted({row['memory.swap.max'] for row in monitors}),
                            'guest_entire_phase_clock_offset_span_s': drift,
                            'reproduced_cgroup_measurement_CPU_seconds': cpu_seconds}
        failed = [x for x in assessment['checks'] if not x['pass']]
        check(f'{directory.name}:all_native_shards_finished', all(x == 0 for x in phase['load_exits']))
        check(f'{directory.name}:explicit_GOMAXPROCS2', all(b['GOMAXPROCS'] == 2 for b in boxes))
        check(f'{directory.name}:GC_logs_parse', all(not b['unparsed_GC_lines'] for b in boxes))
        check(f'{directory.name}:remains_invalid_without_score',
              not assessment['native_qualified'] and not assessment['local_qualified']
              and assessment.get('capacity_score') is None)
        phases.append({
            'id': directory.name, 'users': phase['users'],
            'classification': assessment['classification'],
            'all_classifications': assessment['all_classifications'],
            'native_verdict': assessment['native_verdict'], 'overall': assessment['overall'],
            'failed_top_level_checks': failed, 'PG': pg, 'client_boxes': boxes,
            'budget_raw_and_numeric': budget,
            'target_monitor': assessment['target_monitor'], 'load_monitor': assessment['load_monitor']})
    guard_path = ROOT / 'diagnostics/power-guard-p2-20261023t1811.jsonl'
    guard = rows(guard_path)
    power = [row for row in guard if row['kind'] == 'power']
    epoch = lambda row: datetime.datetime.fromisoformat(row['utc']).timestamp()
    origin = epoch(power[0]) - power[0]['monotonic']
    host_clock_drift = max(abs(epoch(row) - row['monotonic'] - origin) for row in power)
    host = {'polls': len(power), 'all_reported_safe': all(x['safe'] for x in power),
            'max_poll_gap_s': max(b['monotonic'] - a['monotonic'] for a, b in zip(power, power[1:])),
            'max_wall_minus_monotonic_change_s': host_clock_drift, 'exit': guard[-1],
            'meaning': 'Continuous host polls/host clock consistency do not show a sleep recurrence. Guest wall/monotonic failures remain unchanged and are not automatically proof of host sleep.'}
    check('charging_guard_completed_without_abort', host['all_reported_safe'] and guard[-1]['returncode'] == 0 and not guard[-1]['interrupted'])
    stop = read(RUN / 'cases/goose32/stopped.json')
    drop = read(RUN / 'cases/goose32/dropped.json')
    client_final = read(RUN / 'load-final-inspect.json')
    target_final = read(RUN / 'target-final-inspect.json')
    resources = read(RUN / 'final-resource-check.json')
    result = read(RUN / 'diagnostic-result.json')
    check('owned_app_group_stopped_and_database_dropped', bool(stop['stopped_pgid']) and drop['dropped'])
    check('owned_client_stopped_not_OOM', not client_final['State']['Running'] and not client_final['State']['OOMKilled'])
    check('final_resource_receipt_valid', resources['valid'])
    check('diagnostic_completed_without_controller_error', result['error'] is None and result['cases'][0]['status'] == 'DIAGNOSTIC_FIXED_SEQUENCE_COMPLETED')
    top_path = ROOT / 'audit/host-top-p2-20261023t1818.txt'
    top = raw(top_path).decode()
    quiet_gaps = [{'phase': p['id'], 'box': b['index'], **gap}
                  for p in phases for b in p['client_boxes'] for gap in b['longest_sampler_intervals']
                  if gap['wholly_inside_definite_between_collections_gap']]
    quiet_gaps.sort(key=lambda x: x['elapsed_s'], reverse=True)
    summary = {'cycles': len(all_gc),
               'max_individual_STW_ms': max(max(x['sweep_termination_ms'], x['mark_termination_ms']) for x in all_gc),
               'max_concurrent_mark_wall_ms': max(x['concurrent_mark_ms'] for x in all_gc),
               'longest_sampler_interval_wholly_between_completed_collections': quiet_gaps[0],
               'timing_limits': 'GC @ timestamps have no exact runtime-init wall anchor. Definite inter-collection gaps retain the complete -5..0s offset range from the saved launch protocol.'}
    output = {
        'schema': 'independent_completed_P2_diagnostic_review_v1',
        'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'run': str(RUN), 'review_pass': all(x['pass'] for x in checks),
        'scope': 'Saved-file diagnostic analysis only. No Docker, SQL, build, load, source promotion, or rank claim.',
        'source_commit': '23a14e8cbf32113509cd0ad941320ef947508981',
        'binary_sha256': binary_sha, 'capacity_score': None, 'first_place_proven': False,
        'checks': checks, 'phases': phases, 'client_GC_summary': summary,
        'host_power_and_clock': host,
        'host_aggregate_snapshot': {'path': str(top_path.relative_to(ROOT)), 'text': top,
                                    'limit': 'Single aggregate snapshot reports31GiB used/9.7GiB compressor; this does not establish a causal memory-pressure event. The first top CPU display is not used as a current-interval CPU comparison.'},
        'cleanup': {'app_stop': stop, 'database_drop': drop, 'client_state': client_final['State'],
                    'target_state': target_final['State'], 'target_left': 'PG/target running and idle after the diagnostic; owned application and client stopped.'},
        'conclusions': [
            'All three fixed phases completed, but all remain invalid and fail their native SLO. No hold or capacity score exists.',
            'Increasing client GOMAXPROCS to2 did not remove severe timer/active-user failures. The100k/110k client cgroup used about5.80/5.63CPU cores while the target used about3.27/4.02; this is consistent with client/VM scheduling pressure, not proof that the server is fault-free.',
            'No blocker PID was sampled in any phase. The earlier P1 relation-lock episode was not reproduced, and cannot be the necessary explanation for this P2 collapse.',
            'Sampled database work includes idle readers, active execution and WAL sync/write waits. Samples do not identify all queued or unsampled application work.',
            'Completed GC traces show no seconds-long individual STW phase. A48.426-second sampler gap lies wholly between completed collections even with full anchor uncertainty; those recorded collections do not explain it. Allocation/sweeping, descheduling and queued application work are not thereby excluded.',
            'Raw cpu.max changed from800000/100000 to1600000/200000 while retaining exactly8CPU. The frozen exact-string audit flags a budget mismatch; it does not demonstrate more than8CPU. Preserve the original verdicts because real scheduling, timing, active-user and SLO failures remain.',
            'The charging guard remained safe and the host clock stayed consistent within1.27ms. Guest whole-phase clock drift111ms warm/146ms110 is real saved evidence but alone does not prove host sleep.',
            'P1/P2 changes include both client concurrency and observer details, so this is not a pure causal comparison or a performance comparison. Initial collapse cause remains unresolved.'],
        'raw_inputs': inputs}
    OUT.with_suffix('.json').write_text(json.dumps(output, indent=2) + '\n')
    lines = ['# Completed P2 diagnostic review', '',
             'All three phases completed, but none qualified. No capacity score or first-place claim follows.', '',
             '| Users | Recorded classification | p95 / p99, ms | Measured timeouts | PG samples / errors | Sampled blockers |',
             '|---:|---|---:|---:|---:|---:|']
    for p in phases:
        a, pg = p['overall'], p['PG']
        lines.append(f"| {p['users']:,} | {p['classification']} | {a['p95_ms']:.3f} / {a['p99_ms']:.3f} | {a['errors']:,} | {pg['samples']} / {len(pg['errors'])} | {pg['blocking_samples']} |")
    lines += ['', *[paragraph + '\n' for paragraph in output['conclusions']],
              f"Review checks: {sum(x['pass'] for x in checks)}/{len(checks)}. Source/binary: `23a14e8` / `7a7c31fb…`. The runtime was the submitted A revision; the B prototype was not used.", '',
              'Cleanup receipts show the owned app group stopped, clone dropped and client exited without OOM. Target/PostgreSQL remained running and idle; the review did not change them.', '',
              'The JSON retains all numeric waits, GC summaries, raw clock/resource settings and SHA-256 input receipts. This script reads saved files only.']
    OUT.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'review_pass': output['review_pass'], 'checks': len(checks), 'raw_inputs': len(inputs), 'phases': len(phases), 'output': str(OUT)}))


if __name__ == '__main__':
    main()
