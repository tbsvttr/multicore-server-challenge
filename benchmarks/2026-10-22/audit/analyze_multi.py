#!/usr/bin/env python3
"""Audit completed saved two-arm 80k four-shard diagnostics; no Docker/network.

Uses only standard-library file reads and saved evidence. The shared paired
auditor supplies resource/clock accounting; no controller code is imported.
"""
import argparse
import base64
import collections
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import struct
import time
import zlib

from analyze_paired import (EXPECTED_HEAD, GiB, check, events_dict, inspect_budget,
                            jsonl, monitor, read, setting_map, sha)


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


def nofile_diagnosis(directory):
    log = directory / 'server.log'
    if not log.exists(): return None
    with log.open('rb') as stream:
        prefix = stream.read(65536).decode('utf-8', errors='replace')
    evidence = [line for line in prefix.splitlines() if 'Too many open files' in line or 'EMFILE' in line]
    if not evidence: return None
    return {'classification': 'INVALID_TARGET_NOFILE', 'expected_soft_and_hard': 200000,
            'observed_old_child_soft_limit': None, 'observed_old_child_hard_limit': None,
            'reason': 'Actual accept EMFILE occurred. Original app witness did not capture child limits, so inheritance of the intended200000 limit is unverified. A later runuser reproduction is separate evidence, not an old-process measurement.',
            'log_path': str(log), 'log_sha256': sha(log), 'sample_log_lines': evidence[:5]}


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


def assess_attempt(directory, plan, initial, frozen, global_ok):
    checks, warnings = [], []
    state = read(directory / 'assessment.json', {})
    identity = directory.name.split('-', 2)
    out = {'id': directory.name, 'case': state.get('case', identity[2]), 'pair': state.get('pair', int(identity[1][1:])),
           'recorded_classification': state.get('classification', 'INCOMPLETE'), 'recorded_assessment': state,
           'checks': checks, 'warnings': warnings}
    # The old v1 harness omitted child limits. Do not reinterpret a v2 app's
    # genuine FD exhaustion as infrastructure failure after its limits verify.
    nofile = nofile_diagnosis(directory) if plan['controller'] == 'paired-multi-load-v1' else None
    if nofile: out['nofile_invalidity'] = nofile
    required = ['assessment.json', 'database.json', 'app.json', 'before.json', 'after-load.json', 'after.json',
                'stopped.json', 'dropped.json', 'load-commands.json', 'target-monitor.jsonl', 'load-monitor.jsonl', 'merged.json']
    required += [f'box{i}{suffix}' for i in range(4) for suffix in ['.json', '-merged.json']]
    if plan['controller'] in ['paired-multi-load-v2', 'paired-multi-load-v3']:
        required += ['before-load.json', 'app-process-limits.txt', 'app-process-status.txt']
    missing = [name for name in required if not (directory / name).exists()]
    check(checks, 'complete_attempt_evidence', not missing, missing)
    if missing:
        out.update(classification='INVALID_TARGET_NOFILE' if nofile else 'INCOMPLETE' if state.get('classification') == 'INCOMPLETE' or not state else 'INVALID_EVIDENCE', eligible=False)
        return out
    case, protocol = out['case'], plan['protocol']
    app, db, before, live, after = (read(directory / n) for n in ['app.json', 'database.json', 'before.json', 'after-load.json', 'after.json'])
    actual_checks = []
    if plan['controller'] in ['paired-multi-load-v2', 'paired-multi-load-v3']:
        pre = read(directory / 'before-load.json')
        check(checks, 'common_nofile_launch_wrapper', app.get('app_user') == 'challenge'
              and app.get('launch_wrapper') == ['runuser', '-u', 'challenge', '--', 'prlimit', '--nofile=200000:200000', '--'])
        check(checks, 'actual_pre_load_health', pre.get('app_healthy') is True and pre.get('app_pgid') == app['pgid'])
        for label, witness in [('startup', app.get('actual_app')), ('before-load', pre.get('actual_app')), ('after-load', live.get('actual_app'))]:
            actual_checks.extend(actual_process_checks(witness, app, label))
        checks.extend(actual_checks)
        startup = app.get('actual_app', {}).get('processes', [])
        check(checks, 'startup_raw_sidecars_match_actual_process', len(startup) == 1
              and (directory / 'app-process-limits.txt').read_text() == startup[0]['proc_limits']
              and (directory / 'app-process-status.txt').read_text() == startup[0]['proc_status'])
        out['actual_process_witness_checks'] = actual_checks
    raws = [read(directory / f'box{i}.json') for i in range(4)]
    merged = read(directory / 'merged.json')
    commands = read(directory / 'load-commands.json')
    check(checks, 'all_generator_exits_successful', state.get('load_exits') == [0, 0, 0, 0] and state.get('merge_exit') in [0, 3])
    check(checks, 'pinned_binary_launched', app['binary_sha256'] == frozen[case]['binary_sha256'] and app['frozen_binary'] == frozen[case]['frozen_binary'])
    check(checks, 'exact_case_environment', all(app['env'].get(k) == v for k, v in frozen[case]['case']['env'].items()))
    check(checks, 'shared_runtime_contract', app['env'].get('HOST') == '0.0.0.0' and app['env'].get('PORT') == str(plan['configuration']['port'])
          and app['env'].get('JWT_SECRET') == plan['configuration']['jwt_secret']
          and app['env'].get('DATABASE_URL') == 'postgres://conduit:conduit@127.0.0.1:5432/' + db['database'])
    check(checks, 'fresh_full_seed_clone', db['template'] == 'conduit_seed' and db['counts']['users'] == 100000
          and db['counts']['articles'] == 500000 and db['database'] == app['database'] == state['database'])
    out['observed_clone_counts'] = db['counts']
    check(checks, 'post_tail_app_healthy', live.get('app_healthy') is True and live.get('app_pgid') == app['pgid'])
    old, new = events_dict(before['memory.events']), events_dict(live['memory.events'])
    check(checks, 'target_no_new_oom_entire_attempt', all(new.get(k, 0) == old.get(k, 0) for k in ['oom', 'oom_kill', 'oom_group_kill']))
    check(checks, 'owned_app_stopped', read(directory / 'stopped.json').get('stopped_pgid') == app['pgid'])
    check(checks, 'owned_database_dropped', read(directory / 'dropped.json') == {'database': db['database'], 'dropped': True})
    for label, snap in [('before', before), ('after-load', live), ('after', after)]:
        check(checks, label + '_actual_budget', snap.get('cpu.max') == '800000 100000' and snap.get('memory.max') == str(16 * GiB)
              and snap.get('memory.swap.max') == '0' and snap.get('cpuset.cpus') == '')
        check(checks, label + '_official_source_and_head_fixed', snap['official_source_sha256'] == initial['official_source_sha256']
              and snap['repo_head']['stdout'] == EXPECTED_HEAD and snap['repo_head']['exit'] == 0)
        check(checks, label + '_pg_settings_fixed', setting_map(snap) == setting_map(initial))
    metas = [raw['meta'] for raw in raws]
    common = ['run_id', 'start_at_ms', 'ramp_s', 'measure_s', 'tail_s', 'think_scale', 'articles', 'window_start_ms', 'window_end_ms']
    check(checks, 'four_synchronized_raw_windows', all(len({meta[k] for meta in metas}) == 1 for k in common))
    check(checks, 'normal_60_60_15_protocol', all(meta['ramp_s'] == 60 and meta['measure_s'] == 60 and meta['tail_s'] == 15
          and meta['think_scale'] == 1 and meta['articles'] == 500000 and meta['gomaxprocs'] == 1 for meta in metas))
    check(checks, 'exact_native_measurement_window', all(meta['window_start_ms'] == meta['start_at_ms'] + 60000
          and meta['window_end_ms'] == meta['window_start_ms'] + 60000 for meta in metas))
    for i, (meta, command) in enumerate(zip(metas, commands)):
        host = '127.0.0.' + str(i + 1)
        check(checks, f'shard{i}_disjoint_users_and_destination', meta['box_index'] == i and meta['id_offset'] == i * 20000
              and meta['users'] == 20000 and meta['target'] == f'http://{host}:{plan["configuration"]["port"]}')
        flags = dict(zip(command[command.index('run') + 1::2], command[command.index('run') + 2::2]))
        check(checks, f'shard{i}_saved_command_matches_raw', flags.get('-users') == '20000' and flags.get('-box-index') == str(i)
              and flags.get('-id-offset') == str(i * 20000) and flags.get('-start-at') == str(meta['start_at_ms'])
              and flags.get('-run-id') == meta['run_id'] and flags.get('-ramp') == '60s' and flags.get('-measure') == '60s'
              and flags.get('-tail') == '15s' and flags.get('-think-scale') == '1' and flags.get('-articles') == '500000'
              and flags.get('-target') == meta['target'] and flags.get('-secret') == plan['configuration']['jwt_secret']
              and 'GOMAXPROCS=1' in command)
        shard_merged = read(directory / f'box{i}-merged.json')
        checks.extend({'check': f'shard{i}:' + c['check'], **{k: v for k, v in c.items() if k != 'check'}} for c in exact_merge([raws[i]], shard_merged))
        expected = native_verdict(shard_merged, [raws[i]])
        check(checks, f'shard{i}_native_verdict_reproduced', all(shard_merged['verdict'][k] == v for k, v in expected.items()))
    check(checks, 'four_commands_present', len(commands) == 4)
    checks.extend(exact_merge(raws, merged))
    check(checks, 'merged_all_four_shards_80k', merged['users'] == 80000 and len(merged['boxes']) == 4
          and [b['box_index'] for b in merged['boxes']] == list(range(4)) and merged['run_ids'] == [meta['run_id'] for meta in metas])
    expected = native_verdict(merged, raws)
    check(checks, 'native_merged_verdict_reproduced', all(merged['verdict'][k] == v for k, v in expected.items()))
    check(checks, 'assessment_native_results_preserved', state['overall'] == merged['overall'] and state['verdict'] == merged['verdict'])
    overall = merged['overall']
    check(checks, 'count_rps_error_rate_identity', math.isclose(overall['rps'], overall['count'] / 60, rel_tol=1e-12)
          and math.isclose(overall['error_rate'], overall['errors'] / overall['count'] if overall['count'] else 0, rel_tol=1e-12))
    tm = monitor(directory / 'target-monitor.jsonl', metas[0], 8, 16 * GiB)
    load_cpus = 4 if plan['controller'] == 'paired-multi-load-v3' else 2
    lm = monitor(directory / 'load-monitor.jsonl', metas[0], load_cpus, 4 * GiB)
    out.update(target_monitor=tm, load_monitor=lm, native_verdict=merged['verdict'], overall=overall,
               native_boxes=[r['box'] for r in raws], raw_metas=metas, endpoints=merged['endpoints'])
    timeline_errors = sum(second.get('errors', 0) for raw in raws for second in raw.get('timeline', []))
    out.update(native_slo_pass=expected['pass'], zero_measured_errors=overall['errors'] == 0,
               observed_timeline_errors=timeline_errors,
               zero_observed_errors=overall['errors'] == 0 and timeline_errors == 0,
               error_scope='Native SLO/counts apply to the measured60s. Timeline error count includes all recorded ramp/measure/tail seconds.')
    success = overall['count'] - overall['errors']
    metrics = {k: overall[k] for k in ['rps', 'p50_ms', 'p95_ms', 'p99_ms', 'mean_ms', 'errors', 'error_rate']}
    metrics.update(successful_requests=success, successful_rps=success / 60)
    for kind, key in [('total', 'cgroup_cpu_seconds_estimate'), ('app', 'app_cpu_seconds_estimate'), ('pg', 'pg_cpu_seconds_estimate')]:
        cpu = tm.get(key)
        metrics[kind + '_cpu_seconds_estimate'] = cpu
        metrics[kind + '_cpu_pct_of_8'] = cpu / 60 / 8 * 100 if cpu is not None else None
        metrics[kind + '_cpu_ms_per_successful_request_estimate'] = cpu * 1000 / success if cpu is not None and success else None
    out.update(metrics=metrics, raw_run_id=metas[0]['run_id'], window=[metas[0]['window_start_ms'], metas[0]['window_end_ms']])
    invalid = []
    if live.get('app_healthy') is False or any(new.get(k, 0) > old.get(k, 0) for k in ['oom', 'oom_kill', 'oom_group_kill']):
        invalid.append('FAIL_TARGET_RUNTIME')
    if nofile: invalid.append('INVALID_TARGET_NOFILE')
    if actual_checks and not all(c['pass'] for c in actual_checks): invalid.append('INVALID_TARGET_NOFILE')
    if lm.get('cgroup_quota_utilization_pct', 101) > 75 or any(lm.get('oom_delta', {}).values()): invalid.append('INVALID_GENERATOR_CGROUP')
    if expected['lg_limited']: invalid.append('INVALID_GENERATOR')
    if not tm['eligible'] or not lm['eligible']: invalid.append('INVALID_MONITOR')
    if not global_ok or not all(c['pass'] for c in checks): invalid.append('INVALID_EVIDENCE')
    if not expected['pass']: invalid.append('FAIL_SLO')
    out.update(classification=invalid[0] if invalid else 'PASS', all_classifications=invalid or ['PASS'], eligible=not invalid)
    return out


def audit_run(path):
    plan, events = read(path / 'plan.json'), jsonl(path / 'events.jsonl')
    out = {'run': str(path), 'scope': plan['scope'], 'checks': [], 'attempts': [], 'official_score_proven': False,
           'capacity_or_number_one_proven': False, 'all_competitors_beaten': False}
    if not any(e['event'] == 'controller_finished' for e in events):
        out['status'] = 'ACTIVE_NOT_READ'; return out
    checks, initial = out['checks'], read(path / 'target-initial.json')
    research = path.parent.parent
    check(checks, 'frozen_plan_hash', sha(path / 'plan.json') == (path / 'plan.sha256').read_text().strip())
    check(checks, 'exact_80k_protocol', plan['controller'] in ['paired-multi-load-v1', 'paired-multi-load-v2', 'paired-multi-load-v3'] and plan['protocol']['users'] == 80000
          and plan['protocol']['order'] == [[0, 1], [1, 0], [0, 1]]
          and plan['protocol']['shards'] == [{'box_index': i, 'users': 20000, 'id_offset': i * 20000, 'host': f'127.0.0.{i + 1}'} for i in range(4)])
    if plan['controller'] in ['paired-multi-load-v2', 'paired-multi-load-v3']:
        check(checks, 'predeclared_actual_nofile_witness_required', plan['protocol'].get('app_nofile_minimum') == 200000
              and plan['protocol'].get('actual_app_uid_and_limits_required') is True)
    load_cpus = 4 if plan['controller'] == 'paired-multi-load-v3' else 2
    if plan['controller'] == 'paired-multi-load-v3':
        check(checks, 'predeclared_external_client4cpu', plan['protocol'].get('load_cgroup_cpus') == 4)
    out['resource_scope'] = {'target_app_plus_postgres_cpus': 8, 'target_memory_bytes': 16 * GiB,
                             'external_client_cpus': load_cpus, 'external_client_memory_bytes': 4 * GiB,
                             'cpu_per_request_scope': 'Target cgroup only; external client CPU is reported separately.'}
    initial_inspect = {}
    for kind, cpus, memory in [('target', 8, 16 * GiB), ('load', load_cpus, 4 * GiB)]:
        first, last = read(path / (kind + '-inspect.json')), read(path / (kind + '-final-inspect.json'))
        initial_inspect[kind] = first
        check(checks, kind + '_inspect_budgets_and_identity', bool(first) and bool(last) and inspect_budget(first, cpus, memory)
              and inspect_budget(last, cpus, memory) and first['Id'] == last['Id'])
    check(checks, 'generator_separate_cgroup_shared_net', initial_inspect['target']['Id'] != initial_inspect['load']['Id']
          and initial_inspect['load']['HostConfig']['NetworkMode'] == 'container:' + initial_inspect['target']['Id'])
    pg = setting_map(initial)
    check(checks, 'durable_pg18', pg.get('server_version_num', ('',))[0].startswith('18') and pg.get('max_connections', ('',))[0] == '100'
          and pg.get('synchronous_commit', ('',))[0] == 'on' and pg.get('fsync', ('',))[0] == 'on' and pg.get('full_page_writes', ('',))[0] == 'on')
    seed_log = research / 'seed-full.log'
    setup = research / 'setup/upstream-sha256.txt'
    check(checks, 'original_full_seed_fingerprint_pass', 'OK: conduit_seed matches the reference seed' in seed_log.read_text()
          and initial['official_source_sha256']['seed/make-seed.sh'] + '  /work/seed/make-seed.sh' in setup.read_text())
    out['seed_proof'] = {'log_sha256': sha(seed_log), 'script_sha256': initial['official_source_sha256']['seed/make-seed.sh'],
                         'scope': 'Original script checks counts/content fingerprints of all7 tables; each fresh FILE_COPY clone independently checks users/articles only.'}
    frozen = {}
    for case in plan['configuration']['cases']:
        name, root = case['name'], path / 'frozen' / case['name']
        meta = read(root / 'metadata.json'); frozen[name] = meta
        check(checks, name + '_pinned_binary', sha(root / 'app') == meta['binary_sha256'] == case['expected_binary_sha256'])
        actual = {str(f.relative_to(root / 'source')): sha(f) for f in (root / 'source').rglob('*') if f.is_file()}
        check(checks, name + '_all_source_files_frozen', actual == meta['source_sha256'])
        check(checks, name + '_source_manifest_hash', hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest() == meta['source_manifest_sha256'])
        check(checks, name + '_exact_predeclared_case', meta['case'] == case)
    names = [case['name'] for case in plan['configuration']['cases']]
    out.update(reference_case=names[0], candidate_case=names[1], reference_disclosure=plan['configuration'].get('reference_disclosure'))
    if 'rust7' in frozen:
        env = frozen['rust7']['case']['env']
        check(checks, 'rust_8cpu_defaults_and_start_script_exports', all(env.get(k) == v for k, v in {
            'APP_THREADS': '2', 'DB_CONNS': '6', 'DB_WRITE_CONNS': '2', 'BCRYPT_THREADS': '1', 'READ_TAG_ROUTE': '1',
            'READ_COMMENT_SET': '1', 'READ_TAG_BATCH': '1'}.items()))
    if 'goose31_portable' in frozen:
        shared = ['WORKERS', 'PG_READERS', 'HASHERS', 'BCRYPT_BATCH_MS', 'READ_BATCH', 'READ_HOLD']
        check(checks, 'portable_reference_shared_runtime_knobs', all(frozen[names[0]]['case']['env'].get(k)
              == frozen[names[1]]['case']['env'].get(k) for k in shared))
        check(checks, 'portable_reference_explicitly_disclosed', bool(out['reference_disclosure']))
    tools = read(path / 'tool-source-sha256.json')
    if plan['controller'] in ['paired-multi-load-v2', 'paired-multi-load-v3']:
        archived = read(path / 'frozen-tool-sha256.json')
        check(checks, 'actual_run_tool_copies_frozen', all((path / 'tools' / name).exists() and sha(path / 'tools' / name) == h for name, h in archived.items()))
        check(checks, 'tool_hashes_match_frozen_copies', all(
            (archived.get(f) == h) if f in archived else ((research / f).exists() and sha(research / f) == h) for f, h in tools.items()))
    else:
        check(checks, 'tool_hashes_unchanged', all((research / f).exists() and sha(research / f) == h for f, h in tools.items()))
    ordered = [(pair, names[index]) for pair, order in enumerate(plan['protocol']['order'], 1) for index in order]
    expected = [f'{i:02d}-p{pair}-{name}' for i, (pair, name) in enumerate(ordered, 1)]
    directories = sorted(p.name for p in path.iterdir() if p.is_dir() and p.name[:2].isdigit())
    check(checks, 'all_six_planned_attempts_retained_without_replacement', [e['id'] for e in events if e['event'] == 'attempt_start'] == expected
          and directories == sorted(expected) and collections.Counter(e['id'] for e in events if e['event'] == 'attempt_complete') == collections.Counter(expected))
    check(checks, 'controller_no_global_failure', not any(e['event'] == 'controller_error' for e in events)
          and all(e.get('error') is None for e in events if e['event'] == 'controller_finished'))
    attempts = [assess_attempt(path / name, plan, initial, frozen, all(c['pass'] for c in checks)) for name in directories]
    out['attempts'] = attempts
    databases = [a['recorded_assessment'].get('database') for a in attempts]
    check(checks, 'unique_database_each_attempt', len(databases) == len(set(databases)))
    out['pairs'] = []
    for pair in range(1, 4):
        members = [a for a in attempts if a['pair'] == pair]
        valid = len(members) == 2 and {a['case'] for a in members} == set(names) and all(a['eligible'] for a in members)
        clean = valid and all(a.get('zero_observed_errors') is True for a in members)
        result = {'pair': pair, 'slo_and_evidence_qualified': valid, 'qualified': clean,
                  'clean_performance_comparison': clean, 'attempt_ids': [a['id'] for a in members]}
        if valid:
            by = {a['case']: a for a in members}; aa, bb = by[names[0]], by[names[1]]
            result['matched_native_run_id'] = aa['raw_run_id'] == bb['raw_run_id']
            result['qualified'] = clean and result['matched_native_run_id']
            result['clean_performance_comparison'] = result['qualified']
            result['slo_and_evidence_qualified'] = result['matched_native_run_id']
            result['ratios_candidate_over_reference'] = {k: bb['metrics'][k] / v for k, v in aa['metrics'].items()
                if isinstance(v, (int, float)) and v > 0 and isinstance(bb['metrics'].get(k), (int, float)) and bb['metrics'][k] > 0}
            result['change_pct_candidate_vs_reference'] = {k: (v - 1) * 100 for k, v in result['ratios_candidate_over_reference'].items()}
            if not clean: result['comparison_limit'] = 'SLO pass allows <1% measured errors; observed errors exclude this pair from clean performance aggregation.'
        out['pairs'].append(result)
    good = [p for p in out['pairs'] if p['qualified']]
    out['aggregate'] = {}
    if good:
        for metric in set.intersection(*(set(p['ratios_candidate_over_reference']) for p in good)):
            ratios = [p['ratios_candidate_over_reference'][metric] for p in good]
            out['aggregate'][metric] = {'pairs': len(ratios), 'ratios_candidate_over_reference': ratios,
                'geometric_mean_ratio': math.exp(statistics.mean(math.log(x) for x in ratios)), 'all_pairs_lower': all(x < 1 for x in ratios)}
    host = jsonl(path / 'host-memory.jsonl')
    free_percent, swap_used_mib, compressor_pages = [], [], []
    for row in host:
        free = re.search(r'System-wide memory free percentage:\s*(\d+)%', row.get('memory_pressure', {}).get('stdout', ''))
        swap = re.search(r'used\s*=\s*([\d.]+)([MG])', row.get('swapusage', {}).get('stdout', ''))
        compressor = re.search(r'Pages occupied by compressor:\s*(\d+)\.', row.get('vm_stat', {}).get('stdout', ''))
        if free: free_percent.append(int(free[1]))
        if swap: swap_used_mib.append(float(swap[1]) * (1024 if swap[2] == 'G' else 1))
        if compressor: compressor_pages.append(int(compressor[1]))
    out['host_memory_witness'] = {'samples': len(host), 'scope': 'Diagnostic only; shared physical Mac pressure never retroactively excludes attempts.',
        'clock_offsets_range_s': (max((r['wall_ns'] - r['monotonic_ns']) / 1e9 for r in host) - min((r['wall_ns'] - r['monotonic_ns']) / 1e9 for r in host)) if host else None,
        'memory_free_percent_range': [min(free_percent), max(free_percent)] if free_percent else None,
        'host_swap_used_mib_range': [min(swap_used_mib), max(swap_used_mib)] if swap_used_mib else None,
        'compressor_pages_range': [min(compressor_pages), max(compressor_pages)] if compressor_pages else None,
        'collection_errors': sum(any('error' in v or v.get('exit', 0) != 0 for v in r.values() if isinstance(v, dict)) for r in host)}
    out['frozen_identity'] = {name: {k: m[k] for k in ['binary_sha256', 'source_manifest_sha256']} for name, m in frozen.items()}
    out['classification_counts'] = dict(collections.Counter(a['classification'] for a in attempts))
    out['planned_but_not_started'] = [name for name in expected if name not in directories]
    out['clean_performance_pairs'] = len(good)
    out['zero_measured_errors_all_attempts'] = all(a.get('zero_measured_errors') is True for a in attempts)
    out['zero_observed_errors_all_attempts'] = all(a.get('zero_observed_errors') is True for a in attempts)
    out['status'] = 'PASS_LOCAL_EVIDENCE' if all(c['pass'] for c in checks) and all(a['eligible'] for a in attempts) else 'HAS_INVALID_OR_FAILED_ATTEMPTS'
    if any(a['classification'] == 'INVALID_TARGET_NOFILE' for a in attempts): out['status'] = 'INVALID_TARGET_NOFILE'
    out['interpretation'] = 'Four native histograms are verified by exact bin sum. At fixed closed-model load, similar request rates do not establish equal capacity; lower latency or CPU per success is diagnostic only. No warmup/search/5min hold, official x86 score, or ranking proof.'
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/private/tmp/multicore-research-20261022'))
    parser.add_argument('--out', type=Path, default=Path('/private/tmp/multicore-research-20261022/audit/multi-audit.json'))
    args = parser.parse_args()
    if (args.root / 'plan.json').exists(): paths = [args.root]
    elif args.root.name.startswith('paired-multi-load'):
        paths = sorted(p for p in args.root.iterdir() if (p / 'plan.json').exists()) if args.root.exists() else []
    else:
        paths = sorted(p.parent for p in args.root.glob('paired-multi-load*/*/plan.json'))
    report = {'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'analyzer_sha256': sha(Path(__file__)),
              'shared_analyzer_sha256': sha(Path(__file__).with_name('analyze_paired.py')), 'runs': [audit_run(p) for p in paths]}
    report['raw_input_sha256'] = {str(f): sha(f) for p, r in zip(paths, report['runs']) if r['status'] != 'ACTIVE_NOT_READ' for f in p.rglob('*') if f.is_file()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    lines = ['# Independent 80k four-shard audit', '', 'Saved local ARM64 Mac/Docker diagnostics; official rank and capacity are unproven.',
             'Native SLO PASS permits fewer than 1% measured errors. Measured and full recorded timeline errors are listed separately; errorful pairs cannot enter clean performance aggregation.', '']
    for run in report['runs']:
        lines += [f'## {Path(run["run"]).name}', '', f'Status: **{run["status"]}**', '', '| Attempt | Result | Measured errors | Timeline errors | Req/s | p95/p99 ms | Total CPU ms/success |', '|---|---|---:|---:|---:|---:|---:|']
        for attempt in run['attempts']:
            m = attempt.get('metrics', {})
            def fmt(k): return 'unverified' if m.get(k) is None else f'{m[k]:.4f}'
            lines.append(f'| {attempt["id"]} | {attempt["classification"]} | {m.get("errors", "unverified")} | {attempt.get("observed_timeline_errors", "unverified")} | {fmt("rps")} | {fmt("p95_ms")}/{fmt("p99_ms")} | {fmt("total_cpu_ms_per_successful_request_estimate")} |')
        lines += ['', run.get('interpretation', ''), '']
        if run.get('reference_disclosure'): lines += ['Reference disclosure: ' + run['reference_disclosure'], '']
        for pair in run.get('pairs', []):
            if pair['qualified']:
                d = pair['change_pct_candidate_vs_reference']
                lines += [f'Pair {pair["pair"]}, {run["candidate_case"]}/{run["reference_case"]} change: RPS {d.get("rps", 0):+.3f}%; p95 {d.get("p95_ms", 0):+.3f}%; p99 {d.get("p99_ms", 0):+.3f}%; total CPU/success {d.get("total_cpu_ms_per_successful_request_estimate", 0):+.3f}%.', '']
            else: lines += [f'Pair {pair["pair"]}: no clean performance comparison; all attempts retained. ' + pair.get('comparison_limit', ''), '']
    args.out.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'output': str(args.out), 'runs': [{'run': Path(r['run']).name, 'status': r['status'], 'classification_counts': r.get('classification_counts')} for r in report['runs']]}))


if __name__ == '__main__': main()
