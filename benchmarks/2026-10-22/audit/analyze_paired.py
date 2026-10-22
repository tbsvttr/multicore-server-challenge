#!/usr/bin/env python3
"""Independently audit saved paired-load evidence. Never invokes Docker/network.

Read only completed runs unless --allow-incomplete is explicitly supplied.
Output is written outside the raw run trees. CPU estimates interpolate the
bracketing 1 Hz cumulative samples; they are not exact event-level accounting.
"""
import argparse
import bisect
import collections
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

EXPECTED_HEAD = '3e9087473da5c56d5800ae9ee00ac1e84c44a135'
EXPECTED_BINARY = '6ab318a0ab9389dc2e77ec6122ff077a93adbcc183c6285c347104e0f734b6c3'
GiB = 1024 ** 3


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


def audit_attempt(path, run, plan, frozen, global_ok):
    checks, warnings = [], []
    state = read(path / 'assessment.json', {})
    result = {'id': path.name, 'recorded_classification': state.get('classification', 'INCOMPLETE'),
              'recorded_assessment': state, 'checks': checks, 'warnings': warnings, 'path': str(path)}
    identity = path.name.split('-', 2)
    if len(identity) == 3:
        result.update(case=identity[2], pair=int(identity[1][1:]))
    required = ['assessment.json', 'database.json', 'before.json', 'app.json', 'box0.json', 'merged.json',
                'after-load.json', 'after.json', 'stopped.json', 'dropped.json', 'load-command.json',
                'target-monitor.jsonl', 'load-monitor.jsonl']
    missing = [n for n in required if not (path / n).exists()]
    check(checks, 'required_attempt_evidence_complete', not missing, missing)
    if missing:
        result['classification'] = 'INCOMPLETE' if not state else 'INVALID_EVIDENCE'
        result['eligible'] = False
        return result
    case = state['case']
    result.update(case=case, pair=state['pair'])
    app, db, before, after, live = (read(path / n) for n in ['app.json', 'database.json', 'before.json', 'after.json', 'after-load.json'])
    raw, merged, command = (read(path / n) for n in ['box0.json', 'merged.json', 'load-command.json'])
    meta, p = raw['meta'], plan['protocol']
    env = frozen[case]['case']['env']
    check(checks, 'recorded_native_exits', state.get('load_exit') == 0 and state.get('merge_exit') in [0, 3])
    check(checks, 'frozen_binary_launched', app['binary_sha256'] == frozen[case]['binary_sha256'] and app['frozen_binary'] == frozen[case]['frozen_binary'])
    check(checks, 'exact_case_env', all(app['env'].get(k) == v for k, v in env.items()))
    check(checks, 'fresh_full_seed_clone', db['template'] == 'conduit_seed' and db['counts']['users'] == 100000 and db['counts']['articles'] == 500000
          and db['database'] == state['database'] == app['database'])
    result['seed_counts_observed'] = db['counts']
    warnings.append('Per-attempt clone counts cover users/articles only; remaining table counts inherit the named template, not separately sampled.')
    check(checks, 'post_load_server_healthy', live.get('app_healthy') is True and live.get('app_pgid') == app['pgid'])
    check(checks, 'owned_app_group_stopped', read(path / 'stopped.json').get('stopped_pgid') == app['pgid'])
    check(checks, 'owned_database_dropped', read(path / 'dropped.json') == {'database': db['database'], 'dropped': True})
    for name, snap in [('before', before), ('after-load', live), ('after', after)]:
        check(checks, name + '_actual_budget', snap.get('cpu.max') == '800000 100000' and snap.get('memory.max') == str(16 * GiB)
              and snap.get('memory.swap.max') == '0' and snap.get('cpuset.cpus') == '')
        check(checks, name + '_pinned_upstream', snap['repo_head']['stdout'] == EXPECTED_HEAD and snap['repo_head']['exit'] == 0)
        check(checks, name + '_official_source_unchanged', snap['official_source_sha256'] == run['initial']['official_source_sha256'])
        check(checks, name + '_pg_settings_unchanged', setting_map(snap) == setting_map(run['initial']))
    before_memory, after_memory = events_dict(before['memory.events']), events_dict(live['memory.events'])
    check(checks, 'no_target_oom_during_entire_attempt', all(after_memory.get(k, 0) == before_memory.get(k, 0)
          for k in ['oom', 'oom_kill', 'oom_group_kill']))
    check(checks, 'raw_generator_protocol', all(meta.get(k) == p[k] for k in ['users', 'ramp_s', 'measure_s', 'tail_s', 'articles', 'think_scale'])
          and meta.get('gomaxprocs') == 2 and meta.get('id_offset') == 0 and meta.get('box_index') == 0)
    check(checks, 'native_window_exact', meta['window_start_ms'] == meta['start_at_ms'] + p['ramp_s'] * 1000
          and meta['window_end_ms'] - meta['window_start_ms'] == p['measure_s'] * 1000)
    flags = dict(zip(command[command.index('run') + 1::2], command[command.index('run') + 2::2]))
    check(checks, 'saved_command_protocol', flags.get('-users') == str(p['users']) and flags.get('-ramp') == str(p['ramp_s']) + 's'
          and flags.get('-measure') == str(p['measure_s']) + 's' and flags.get('-tail') == str(p['tail_s']) + 's'
          and flags.get('-articles') == '500000' and flags.get('-think-scale') == '1' and flags.get('-run-id') == meta['run_id'])
    check(checks, 'native_merged_protocol', merged['users'] == p['users'] and merged['ramp_s'] == p['ramp_s']
          and merged['measure_s'] == p['measure_s'] and merged['run_ids'] == [meta['run_id']])
    overall, verdict = merged['overall'], merged['verdict']
    raw_count = sum(x['count'] for x in raw['endpoints'].values())
    raw_errors = sum(sum(x.get('errors', {}).values()) for x in raw['endpoints'].values())
    raw_statuses = collections.Counter()
    for x in raw['endpoints'].values(): raw_statuses.update(x.get('statuses', {}))
    check(checks, 'raw_counts_statuses_errors_match_merge', raw_count == overall['count'] and raw_errors == overall['errors']
          and dict(raw_statuses) == overall['statuses'])
    check(checks, 'raw_rps_count_identity', math.isclose(overall['rps'], overall['count'] / p['measure_s'], rel_tol=1e-12))
    check(checks, 'raw_error_rate_identity', math.isclose(overall['error_rate'], overall['errors'] / overall['count'] if overall['count'] else 0, rel_tol=1e-12))
    native_lg = raw['box'].get('fell_behind', False) or raw['box']['cpu_avg_measure_pct'] > 75
    native_pass = overall['count'] > 0 and overall['p95_ms'] < 500 and overall['p99_ms'] < 1000 and overall['error_rate'] < .01
    check(checks, 'native_verdict_reproduced', verdict['pass'] == native_pass and verdict['lg_limited'] == native_lg)
    check(checks, 'assessment_native_values_unchanged', state['overall'] == overall and state['verdict'] == verdict)
    tm = monitor(path / 'target-monitor.jsonl', meta, 8, 16 * GiB)
    lm = monitor(path / 'load-monitor.jsonl', meta, 2, 4 * GiB)
    result.update(target_monitor=tm, load_monitor=lm, native_verdict=verdict, overall=overall, endpoints=merged['endpoints'],
                  raw_meta=meta, native_generator_box=raw['box'])
    successful = overall['count'] - overall['errors']
    duration = p['measure_s']
    metrics = {k: overall[k] for k in ['rps', 'p50_ms', 'p95_ms', 'p99_ms', 'mean_ms', 'errors', 'error_rate']}
    metrics.update(successful_requests=successful, successful_rps=successful / duration)
    for label, key in [('total', 'cgroup_cpu_seconds_estimate'), ('app', 'app_cpu_seconds_estimate'), ('pg', 'pg_cpu_seconds_estimate')]:
        cpu = tm.get(key)
        metrics[label + '_cpu_seconds_estimate'] = cpu
        metrics[label + '_cpu_pct_of_8'] = cpu / duration / 8 * 100 if cpu is not None else None
        metrics[label + '_cpu_ms_per_successful_request_estimate'] = cpu * 1000 / successful if cpu is not None and successful else None
    result['metrics'] = metrics
    result['raw_run_id'] = meta['run_id']
    result['window'] = [meta['window_start_ms'], meta['window_end_ms']]
    issues = []
    if not global_ok or not all(c['pass'] for c in checks): issues.append('INVALID_EVIDENCE')
    if not tm['eligible'] or not lm['eligible']: issues.append('INVALID_MONITOR')
    if native_lg: issues.append('INVALID_GENERATOR')
    if lm.get('cgroup_quota_utilization_pct', 101) > p.get('load_cgroup_cpu_limit_pct', 75): issues.append('INVALID_GENERATOR_CGROUP')
    if not native_pass: issues.append('FAIL_SLO')
    result['all_classifications'] = issues or ['PASS']
    result['classification'] = issues[0] if issues else 'PASS'
    result['eligible'] = not issues
    return result


def audit_run(path, allow_incomplete):
    checks, warnings = [], []
    plan, events = read(path / 'plan.json'), jsonl(path / 'events.jsonl')
    complete = any(e['event'] == 'controller_finished' for e in events)
    if not complete and not allow_incomplete:
        return {'run': str(path), 'status': 'ACTIVE_NOT_READ', 'scope': plan['scope'], 'attempts': []}
    initial = read(path / 'target-initial.json', {})
    run = {'run': str(path), 'scope': plan['scope'], 'smoke': plan['protocol']['smoke'], 'controller_finished': complete,
           'checks': checks, 'warnings': warnings, 'initial': initial}
    research = path.parent.parent
    seed_log, seed_setup = research / 'seed-full.log', research / 'setup/upstream-sha256.txt'
    reference_seed_sha = initial.get('official_source_sha256', {}).get('seed/make-seed.sh')
    check(checks, 'full_template_original_fingerprint_pass', seed_log.exists() and seed_setup.exists()
          and 'OK: conduit_seed matches the reference seed' in seed_log.read_text()
          and reference_seed_sha + '  /work/seed/make-seed.sh' in seed_setup.read_text())
    run['full_seed_proof'] = {'scope': 'Original seed script validates count and summed row-content MD5 fingerprint for all7 tables. Clone checks independently count users/articles only; remaining identity inherits fresh FILE_COPY template.',
        'proof_log': str(seed_log), 'proof_log_sha256': sha(seed_log) if seed_log.exists() else None,
        'seed_script_sha256': reference_seed_sha,
        'reference_row_counts': {'users': 100000, 'follows': 1989808, 'articles': 500000, 'tags': 200,
                                 'article_tags': 1250377, 'favorites': 4990637, 'comments': 2494001}}
    check(checks, 'plan_raw_hash_matches_frozen', sha(path / 'plan.json') == (path / 'plan.sha256').read_text().strip())
    target, load = read(path / 'target-inspect.json'), read(path / 'load-inspect.json')
    check(checks, 'target_initial_inspect_budget', inspect_budget(target, 8, 16 * GiB))
    check(checks, 'load_initial_inspect_budget', inspect_budget(load, 2, 4 * GiB))
    check(checks, 'load_separate_cgroup_shared_net', target['Id'] != load['Id'] and load['HostConfig']['NetworkMode'] == 'container:' + target['Id'])
    for kind, cpus, memory in [('target', 8, 16 * GiB), ('load', 2, 4 * GiB)]:
        final = read(path / (kind + '-final-inspect.json'))
        check(checks, kind + '_final_inspect_budget', bool(final) and inspect_budget(final, cpus, memory))
        check(checks, kind + '_container_identity_stable', bool(final) and final['Id'] == (target if kind == 'target' else load)['Id'])
    check(checks, 'pinned_upstream_head', initial.get('repo_head', {}).get('stdout') == EXPECTED_HEAD)
    pg = setting_map(initial)
    check(checks, 'pg18_synchronous_durable', pg.get('server_version_num', ('',))[0].startswith('18')
          and pg.get('max_connections', ('',))[0] == '100' and pg.get('synchronous_commit', ('',))[0] == 'on'
          and pg.get('fsync', ('',))[0] == 'on' and pg.get('full_page_writes', ('',))[0] == 'on')
    frozen = {}
    for case in plan['configuration']['cases']:
        name, directory = case['name'], path / 'frozen' / case['name']
        meta = read(directory / 'metadata.json')
        frozen[name] = meta
        manifest = meta['source_sha256']
        check(checks, name + '_binary_pinned_and_unchanged', sha(directory / 'app') == meta['binary_sha256'] == EXPECTED_BINARY)
        actual = {str(f.relative_to(directory / 'source')): sha(f) for f in (directory / 'source').rglob('*') if f.is_file()}
        check(checks, name + '_all_source_files_frozen', actual == manifest)
        check(checks, name + '_source_manifest_hash', hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest() == meta['source_manifest_sha256'])
        check(checks, name + '_case_configuration_matches_plan', meta['case'] == case)
    names = list(frozen)
    check(checks, 'arms_same_binary_source', frozen[names[0]]['binary_sha256'] == frozen[names[1]]['binary_sha256']
          and frozen[names[0]]['source_sha256'] == frozen[names[1]]['source_sha256'])
    env0, env1 = (frozen[n]['case']['env'] for n in names)
    check(checks, 'only_article_batch_toggle_differs', env0.get('ARTICLE_BATCH') == '0' and env1.get('ARTICLE_BATCH') == '1'
          and {k: v for k, v in env0.items() if k != 'ARTICLE_BATCH'} == {k: v for k, v in env1.items() if k != 'ARTICLE_BATCH'})
    root = research
    tool_hashes = read(path / 'tool-source-sha256.json')
    check(checks, 'tool_files_still_match_frozen_hashes', all((root / f).exists() and sha(root / f) == h for f, h in tool_hashes.items()))
    expected, serial = [], 0
    for pair, order in enumerate(plan['protocol']['order'], 1):
        for index in order:
            serial += 1
            expected.append(f'{serial:02d}-p{pair}-{plan["configuration"]["cases"][index]["name"]}')
    started = [e['id'] for e in events if e['event'] == 'attempt_start']
    directories = sorted(p.name for p in path.iterdir() if p.is_dir() and p.name[:2].isdigit())
    check(checks, 'all_planned_attempts_retained_once_no_replacement', started == expected and directories == sorted(expected),
          {'planned': expected, 'started': started, 'directories': directories})
    check(checks, 'all_attempts_completed_once', collections.Counter(e['id'] for e in events if e['event'] == 'attempt_complete') == collections.Counter(expected))
    check(checks, 'controller_no_top_level_failure', complete and not any(e['event'] == 'controller_error' for e in events)
          and all(e.get('error') is None for e in events if e['event'] == 'controller_finished'))
    run['frozen_identity'] = {n: {k: frozen[n][k] for k in ['binary_sha256', 'source_manifest_sha256']} for n in names}
    run['attempts'] = [audit_attempt(path / n, run, plan, frozen, all(c['pass'] for c in checks)) for n in directories]
    attempts = run['attempts']
    databases = [r['recorded_assessment'].get('database') for r in attempts]
    check(checks, 'fresh_unique_database_every_attempt', len(databases) == len(set(databases)))
    run['pairs'] = []
    for pair in range(1, len(plan['protocol']['order']) + 1):
        members = [r for r in attempts if r.get('pair') == pair]
        qualified = not run['smoke'] and len(members) == 2 and {r['case'] for r in members} == set(names) and all(r['eligible'] for r in members)
        row = {'pair': pair, 'qualified': qualified, 'attempt_ids': [r['id'] for r in members]}
        if qualified:
            by = {r['case']: r for r in members}; aa, bb = (by[n] for n in names)
            check(row.setdefault('checks', []), 'matched_native_random_stream', aa['raw_run_id'] == bb['raw_run_id'])
            row['qualified'] = all(c['pass'] for c in row['checks'])
            ratios = {}
            for metric, av in aa['metrics'].items():
                bv = bb['metrics'].get(metric)
                if isinstance(av, (int, float)) and isinstance(bv, (int, float)) and av > 0 and bv > 0:
                    ratios[metric] = bv / av
            row['ratios_on_over_off'] = ratios
            row['change_pct_on_vs_off'] = {k: (v - 1) * 100 for k, v in ratios.items()}
        run['pairs'].append(row)
    good = [r for r in run['pairs'] if r['qualified']]
    aggregate = {}
    if good:
        metrics = set.intersection(*(set(r['ratios_on_over_off']) for r in good))
        for metric in sorted(metrics):
            ratios = [r['ratios_on_over_off'][metric] for r in good]
            aggregate[metric] = {'pairs': len(ratios), 'ratios_on_over_off': ratios,
                                 'geometric_mean_ratio': math.exp(statistics.mean(math.log(x) for x in ratios)),
                                 'all_pairs_lower': all(x < 1 for x in ratios)}
    run['aggregate'] = aggregate
    run['classification_counts'] = dict(collections.Counter(r['classification'] for r in attempts))
    run['status'] = 'PASS_LOCAL_EVIDENCE' if complete and all(c['pass'] for c in checks) and all(r['eligible'] for r in attempts) else 'INCOMPLETE' if not complete else 'HAS_INVALID_OR_FAILED_ATTEMPTS'
    run['official_score_proven'] = False
    run['capacity_or_number_one_proven'] = False
    run['all_competitors_beaten'] = False
    run['interpretation'] = 'Closed-model fixed unsaturated load: similar req/s is expected and cannot establish capacity, a maximum user count, or rank.'
    run['cpu_accounting'] = 'CPU seconds are bracketing 1Hz counter interpolation estimates. Total is target cgroup; app/PG are live-process sums and withheld on population change. PG RSS sums double-count shared pages; combined memory is cgroup memory.current.'
    # This screening policy is explicit in the analyzer source; it is not an official scoring criterion.
    cpu = aggregate.get('total_cpu_ms_per_successful_request_estimate', {})
    all_three = len(good) == 3 and len(attempts) == 6
    tail_ok = all(r['ratios_on_over_off'].get(k, 99) <= 1.05 for r in good for k in ['p95_ms', 'p99_ms'])
    zero_errors = all(r.get('overall', {}).get('errors') == 0 for r in attempts)
    recommend = all_three and zero_errors and cpu.get('all_pairs_lower', False) and cpu.get('geometric_mean_ratio', 99) <= .95 and tail_ok
    run['feature_screening'] = {'policy': 'Retain default-off unless all3 pairs eligible/zero errors, target CPU per successful request improves in every pair and geometric mean >=5%, with no per-pair p95/p99 regression >5%. Diagnostic only.',
                                'recommend_enabled_for_further_capacity_testing': recommend,
                                'result': 'MEETS_LOCAL_DIAGNOSTIC_SCREEN' if recommend else 'KEEP_DEFAULT_OFF_INSUFFICIENT_OR_INCONSISTENT_GAIN'}
    del run['initial']
    return run


def markdown(report):
    lines = ['# Independent local paired-load audit', '',
             'These are saved ARM64 Mac/Docker diagnostics. No official score, capacity limit, #1 rank, or win over all competitors is established.', '']
    for run in report['runs']:
        lines += [f'## {Path(run["run"]).name}', '', f'Status: **{run["status"]}**. Scope: {run["scope"]}.', '']
        if not run['attempts']: continue
        lines += ['| Attempt | Result | Req/s | p95 / p99 ms | App / PG / total CPU % of8 | Total CPU ms/success |', '|---|---|---:|---:|---:|---:|']
        def number(v, digits=3): return 'unverified' if v is None else f'{v:,.{digits}f}'
        for attempt in run['attempts']:
            m = attempt.get('metrics', {})
            lines.append('| ' + ' | '.join([attempt['id'], attempt['classification'], number(m.get('rps')),
                number(m.get('p95_ms')) + ' / ' + number(m.get('p99_ms')),
                ' / '.join(number(m.get(k + '_cpu_pct_of_8')) for k in ['app', 'pg', 'total']),
                number(m.get('total_cpu_ms_per_successful_request_estimate'))]) + ' |')
        lines += ['', run.get('cpu_accounting', ''), '', f'Feature screening: **{run.get("feature_screening", {}).get("result", "unavailable")}**.', '']
        for pair in run.get('pairs', []):
            if pair['qualified']:
                changes = pair['change_pct_on_vs_off']
                lines.append(f'Pair{pair["pair"]}, on versus off: RPS {changes.get("rps", 0):+.3f}%; p95 {changes.get("p95_ms", 0):+.3f}%; p99 {changes.get("p99_ms", 0):+.3f}%; total CPU/success {changes.get("total_cpu_ms_per_successful_request_estimate", 0):+.3f}%.')
            else: lines.append(f'Pair{pair["pair"]}: unqualified; retained without replacement.')
        failed = [c for c in run.get('checks', []) if not c['pass']]
        if failed: lines += ['', 'Failed run checks: ' + ', '.join(c['check'] for c in failed) + '.']
        for attempt in run['attempts']:
            failed = [c['check'] for c in attempt['checks'] if not c['pass']]
            failed += [f'{which}:{c["check"]}' for which in ['target_monitor', 'load_monitor'] for c in attempt.get(which, {}).get('checks', []) if not c['pass']]
            if failed: lines += ['', attempt['id'] + ': ' + ', '.join(failed) + '.']
        lines.append('')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/private/tmp/multicore-research-20261022/paired-load'))
    parser.add_argument('--out', type=Path, default=Path('/private/tmp/multicore-research-20261022/audit/paired-audit.json'))
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    paths = [args.root] if (args.root / 'plan.json').exists() else sorted(p for p in args.root.iterdir() if (p / 'plan.json').exists())
    report = {'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'analyzer_sha256': sha(Path(__file__)),
              'read_only_inputs': True, 'runs': [audit_run(p, args.allow_incomplete) for p in paths]}
    hashes = {}
    for path, run in zip(paths, report['runs']):
        if run['status'] == 'ACTIVE_NOT_READ': continue
        for file in path.rglob('*'):
            if file.is_file(): hashes[str(file)] = sha(file)
    report['raw_input_sha256'] = hashes
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    args.out.with_suffix('.md').write_text(markdown(report))
    print(json.dumps({'output': str(args.out), 'runs': [{'run': Path(r['run']).name, 'status': r['status'],
                      'attempts': len(r['attempts']), 'classification_counts': r.get('classification_counts')} for r in report['runs']]}))


if __name__ == '__main__': main()
