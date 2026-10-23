"""Recompute qualification from saved native results and kernel witnesses."""
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from search_policy import client_cpu_scope_policy, load_cpus, load_memory_bytes, shards
from .primitives import (GiB, actual_process_checks, check, events_dict, exact_merge, generator_details,
                         jsonl, monitor, native_verdict, read, setting_map, sha)


def conformance(case_dir, case):
    declared = case.get('conformance', {})
    log = case_dir / 'conformance.log'
    return bool(declared.get('passed') is True and declared.get('checks_passed') == declared.get('checks_total') == 197
                and declared.get('binary_sha256') == case.get('expected_binary_sha256')
                and log.exists() and sha(log) == declared.get('log_sha256')
                and '197 steps, 197 passed, 0 failed' in log.read_text()
                and 'RESULT: PASS' in log.read_text())


def audit_phase(directory, case_dir, plan, case, initial, global_valid=True):
    state = read(directory / 'phase.json', {})
    out = {k: state.get(k) for k in ['id', 'case', 'stage', 'users', 'run_id', 'database', 'session_id']}
    out.update(recorded_classification=read(directory / 'assessment.json', {}).get('classification'),
               checks=[], classification='INCOMPLETE', eligible=False, valid_server_failure=False)
    checks = out['checks']
    count = len(state.get('shards', []))
    required = ['phase.json', 'before-load.json', 'after-load.json', 'target-monitor.jsonl', 'load-monitor.jsonl',
                'merged.json', 'load-commands.json'] + [f'box{i}.json' for i in range(count)]
    missing = [name for name in required if not (directory / name).exists()]
    check(checks, 'complete_saved_phase', not missing and count > 0, missing)
    if missing or count == 0:
        return out
    try:
        protocol = plan['protocol']
        client_memory = load_memory_bytes(protocol, plan['configuration'])
        client_cpus = load_cpus(protocol, plan['configuration'])
        cpu_scope = client_cpu_scope_policy(protocol, plan['configuration'])
        expected_stage = protocol[state['stage']]
        expected_shards = shards(state['users'], protocol)
        app, db = read(case_dir / 'app.json'), read(case_dir / 'database.json')
        before, after = read(directory / 'before-load.json'), read(directory / 'after-load.json')
        raws = [read(directory / f'box{i}.json') for i in range(count)]
        merged, commands = read(directory / 'merged.json'), read(directory / 'load-commands.json')
        check(checks, 'predeclared_balanced_shards_and_limits', state['shards'] == expected_shards
              and sum(s['users'] for s in expected_shards) == state['users'] and 1 <= count <= 8)
        check(checks, 'single_database_and_continuous_app_session', state['database'] == db['database'] == app['database']
              and state['session_id'] == case_dir.name and db['template'] == 'conduit_seed'
              and db['counts']['users'] == 100000 and db['counts']['articles'] == 500000)
        check(checks, 'declared_binary_env_and_common_runtime', app['binary_sha256'] == case['expected_binary_sha256']
              and all(app['env'].get(k) == v for k, v in case['env'].items())
              and app['env'].get('HOST') == '0.0.0.0' and app['env'].get('PORT') == str(plan['configuration']['port'])
              and app['env'].get('JWT_SECRET') == plan['configuration']['jwt_secret'])
        for label, snap in [('before', before), ('after', after)]:
            check(checks, label + ':fixed_target_budget', snap.get('cpu.max') == '800000 100000'
                  and snap.get('memory.max') == str(16 * GiB) and snap.get('memory.swap.max') == '0'
                  and snap.get('cpuset.cpus') == '')
            check(checks, label + ':official_sources_and_pg_settings_fixed',
                  snap['official_source_sha256'] == initial['official_source_sha256']
                  and snap['repo_head'] == initial['repo_head']
                  and setting_map(snap) == setting_map(initial))
        startup = actual_process_checks(app.get('actual_app'), app, 'startup')
        pre = actual_process_checks(before.get('actual_app'), app, 'before')
        post = actual_process_checks(after.get('actual_app'), app, 'after') if after.get('app_healthy') is True else []
        checks.extend(startup + pre + post)
        check(checks, 'app_healthy_before_load', before.get('app_healthy') is True and before.get('app_pgid') == app['pgid'])
        check(checks, 'after_health_witness_present', isinstance(after.get('app_healthy'), bool))
        check(checks, 'all_native_processes_exited_normally', state.get('load_exits') == [0] * count
              and state.get('merge_exit') in [0, 3])
        metas = [r['meta'] for r in raws]
        common = ['run_id', 'start_at_ms', 'ramp_s', 'measure_s', 'tail_s', 'think_scale', 'articles', 'window_start_ms', 'window_end_ms']
        check(checks, 'synchronized_raw_windows', all(len({m[k] for m in metas}) == 1 for k in common))
        check(checks, 'native_metadata_exact_stage_protocol', all(
              all(m[k] == expected_stage[k] for k in ['ramp_s', 'measure_s', 'tail_s'])
              and m['articles'] == 500000 and m['think_scale'] == 1 and m['gomaxprocs'] == 1
              and m['run_id'] == state['run_id'] and m['window_start_ms'] == m['start_at_ms'] + expected_stage['ramp_s'] * 1000
              and m['window_end_ms'] == m['window_start_ms'] + expected_stage['measure_s'] * 1000 for m in metas))
        check(checks, 'one_saved_command_per_shard', len(commands) == count)
        for i, (raw, expected) in enumerate(zip(raws, expected_shards)):
            meta = raw['meta']
            check(checks, f'shard{i}:exact_users_ids_destination', all(meta[k] == expected[k] for k in ['box_index', 'users', 'id_offset'])
                  and meta['target'] == f"http://{expected['host']}:{plan['configuration']['port']}")
            command = commands[i]
            flags = dict(zip(command[command.index('run') + 1::2], command[command.index('run') + 2::2]))
            values = {'-users': str(expected['users']), '-box-index': str(i), '-id-offset': str(expected['id_offset']),
                      '-start-at': str(meta['start_at_ms']), '-run-id': meta['run_id'], '-target': meta['target'],
                      '-ramp': str(expected_stage['ramp_s']) + 's', '-measure': str(expected_stage['measure_s']) + 's',
                      '-tail': str(expected_stage['tail_s']) + 's', '-articles': '500000', '-think-scale': '1',
                      '-secret': plan['configuration']['jwt_secret']}
            check(checks, f'shard{i}:raw_command_agrees', all(flags.get(k) == v for k, v in values.items()) and 'GOMAXPROCS=1' in command)
            check(checks, f'shard{i}:at_least99pct_vus_active', raw['box'].get('active_vus_at_window_start', 0) >= .99 * expected['users'])
        checks.extend(exact_merge(raws, merged))
        check(checks, 'merged_all_shards_and_users', merged['users'] == state['users'] and len(merged['boxes']) == count
              and [b['box_index'] for b in merged['boxes']] == list(range(count))
              and merged['run_ids'] == [m['run_id'] for m in metas])
        verdict = native_verdict(merged, raws)
        check(checks, 'native_verdict_reproduced', all(merged['verdict'][k] == v for k, v in verdict.items()))
        details = generator_details(raws, merged)
        checks.extend(details['checks'])
        overall, seconds = merged['overall'], expected_stage['measure_s']
        check(checks, 'request_rate_and_errors_reproduced',
              math.isclose(overall['rps'], overall['count'] / seconds, rel_tol=1e-12)
              and math.isclose(overall['error_rate'], overall['errors'] / overall['count'] if overall['count'] else 0, rel_tol=1e-12))
        tm = monitor(directory / 'target-monitor.jsonl', metas[0], 8, 16 * GiB)
        lm = monitor(directory / 'load-monitor.jsonl', metas[0], client_cpus, client_memory)
        clock_checks = []
        for label in ['target', 'load']:
            rows = jsonl(directory / (label + '-monitor.jsonl'))
            offsets = [(r['wall_ns'] - r['monotonic_ns']) / 1e9 for r in rows]
            drift = max(offsets) - min(offsets) if offsets else None
            check(clock_checks, label + ':entire_phase_clock_drift_under100ms', drift is not None and drift < .1, drift)
        checks.extend(clock_checks)
        old, new = events_dict(before['memory.events']), events_dict(after['memory.events'])
        target_oom = {k: new.get(k, 0) - old.get(k, 0) for k in ['oom', 'oom_kill', 'oom_group_kill']}
        target_failed = after.get('app_healthy') is False or any(target_oom.values())
        out.update(overall=overall, native_verdict=merged['verdict'], target_monitor=tm, load_monitor=lm,
                   declared_load_memory_bytes=client_memory,
                   declared_load_cpus=client_cpus,
                   client_cpu_scope_policy=cpu_scope,
                   classification_scope='independent_local' if cpu_scope == 'dedicated_client_cgroup_v1' else 'native_generator_and_SLO',
                   native_qualified=verdict['pass'] and not verdict['lg_limited'],
                   native_whole_vm_CPU_flagged_shards=details['whole_vm_CPU_flagged_shards'],
                   native_whole_vm_CPU_flag_count=len(details['whole_vm_CPU_flagged_shards']),
                   target_oom_delta=target_oom, post_load_healthy=after.get('app_healthy'),
                   zero_measured_errors=overall['errors'] == 0,
                   observed_timeline_errors=sum(s.get('errors', 0) for r in raws for s in r.get('timeline', [])),
                   conformance_197_full_seed_proven=conformance(case_dir, case))
        success = overall['count'] - overall['errors']
        out['cpu_ms_per_successful_request_sampled_estimate'] = tm.get('cgroup_cpu_seconds_estimate', 0) * 1000 / success if success and tm['eligible'] else None
        invalid = []
        if not all(c['pass'] for c in clock_checks):
            invalid.append('INVALID_CLOCK')
        cpu_only_exception = (cpu_scope == 'dedicated_client_cgroup_v1'
                              and bool(details['whole_vm_CPU_flagged_shards'])
                              and not details['timing_failed_shards']
                              and all(c['pass'] for c in details['checks']))
        out['local_whole_vm_CPU_scope_exception'] = cpu_only_exception
        if verdict['lg_limited'] and not cpu_only_exception:
            invalid.append('INVALID_GENERATOR')
        if lm.get('cgroup_quota_utilization_pct', 101) > 75 or any(lm.get('oom_delta', {}).values()):
            invalid.append('INVALID_GENERATOR_CGROUP')
        target_sampling_valid = tm['eligible'] or (any(target_oom.values()) and all(
            c['pass'] or c['check'] == 'no_measurement_oom' for c in tm['checks']))
        if not target_sampling_valid or not lm['eligible']:
            invalid.append('INVALID_MONITOR')
        if not global_valid or not all(c['pass'] for c in checks):
            invalid.append('INVALID_EVIDENCE')
        if target_failed:
            invalid.append('FAIL_TARGET_RUNTIME')
        if not verdict['pass']:
            invalid.append('FAIL_SLO')
        out.update(classification=invalid[0] if invalid else 'PASS', all_classifications=invalid or ['PASS'],
                   eligible=not invalid, local_qualified=not invalid, valid_server_failure=invalid == ['FAIL_SLO'])
    except (KeyError, IndexError, ValueError, TypeError, OSError, ArithmeticError) as error:
        out.update(classification='INVALID_EVIDENCE', error=type(error).__name__ + ': ' + str(error))
    return out
