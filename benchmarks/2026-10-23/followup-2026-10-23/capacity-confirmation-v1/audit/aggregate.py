#!/usr/bin/env python3
"""Audit completed selected-point confirmation; never infer a new capacity maximum."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from search_policy import DEFAULT_PROTOCOL, client_gomaxprocs, client_cpu_scope_policy, growth_factor, load_cpus, load_memory_bytes, next_action
from audit.evidence import audit_phase, conformance
from capacity_controller import CONFIRMATION_MODE, confirmation_actions, validate_confirmation
from audit.primitives import GiB, check, inspect_budget, jsonl, read, setting_map, sha


def audit_run(root):
    plan, events = read(root / 'plan.json'), jsonl(root / 'events.jsonl')
    result = {'run': str(root), 'checks': [], 'rows': [], 'official_rank_proven': False,
              'all_competitors_beaten': False, 'capacity_maximum_established': False, 'scope': plan['scope']}
    if not any(e['event'] == 'controller_finished' for e in events):
        result['status'] = 'ACTIVE_NOT_READ'
        return result
    checks = result['checks']
    required = ['target-initial.json', 'target-inspect.json', 'target-final-inspect.json', 'load-inspect.json',
                'load-final-inspect.json', 'native-sha256.txt', 'tool-sha256.json', 'final-resource-check.json']
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        result.update(status='INCOMPLETE_INFRASTRUCTURE', missing=missing,
                      rows=[{'case': c['name'], 'status': 'INCOMPLETE_INFRASTRUCTURE', 'capacity_users': None,
                             'phase_paths_retained': [str(p) for p in (root / 'cases' / c['name'] / 'phases').glob('*')]} for c in plan['configuration']['cases']])
        return result
    check(checks, 'plan_hash_fixed', sha(root / 'plan.json') == (root / 'plan.sha256').read_text().strip())
    check(checks, 'explicit_confirmation_only_mode', plan.get('schema') == 'multicore-local-confirmation-v1'
          and plan.get('study_mode') == CONFIRMATION_MODE and plan.get('capacity_search_disabled') is True)
    started_cases = [event.get('case') for event in events if event.get('event') == 'case_start']
    selected_order = [case['name'] for case in plan['configuration']['cases']]
    present_cases = [name for name in selected_order if (root / 'cases' / name).is_dir()]
    check(checks, 'reverse_order_case_starts_preserved', started_cases == selected_order[:len(started_cases)]
          and started_cases == present_cases and len(started_cases) == len(set(started_cases)))
    try:
        validate_confirmation(plan['configuration'])
        reference_valid = True
    except (KeyError, TypeError, ValueError, OSError):
        reference_valid = False
    check(checks, 'selected_points_bound_to_completed_first_study', reference_valid)
    result['first_study_audit'] = plan['configuration'].get('first_study_audit')
    result['first_study_audit_sha256'] = plan['configuration'].get('first_study_audit_sha256')

    try:
        gomax = client_gomaxprocs(plan['protocol'], plan['configuration'])
        client_memory = load_memory_bytes(plan['protocol'], plan['configuration'])
        client_cpus = load_cpus(plan['protocol'], plan['configuration'])
        cpu_scope = client_cpu_scope_policy(plan['protocol'], plan['configuration'])
        growth = growth_factor(plan['protocol'], plan['configuration'])
        declared_load_valid = True
    except (KeyError, TypeError, ValueError):
        client_memory, client_cpus, cpu_scope, growth, declared_load_valid = 0, 0, None, None, False
    check(checks, 'explicit_external_client_memory_and_cpu_declared', declared_load_valid
          and plan['configuration'].get('load_memory_bytes') == client_memory
          and plan['configuration'].get('load_cpus') == client_cpus)
    check(checks, 'client_CPU_scope_policy_explicitly_preregistered', declared_load_valid
          and plan['configuration'].get('client_cpu_scope_policy') == cpu_scope)
    result['client_cpu_scope_policy'] = cpu_scope
    check(checks, 'growth_factor_explicitly_preregistered', declared_load_valid
          and plan['configuration'].get('growth_factor') == growth)
    result['growth_factor'] = growth
    check(checks, 'fixed_server_budget_and_local_rounding_policy',
          plan['protocol'].get('target_cpus') == 8 and plan['protocol'].get('target_memory_bytes') == 16 * GiB
          and plan['protocol'].get('rounding_policy') == DEFAULT_PROTOCOL['rounding_policy'])
    result['declared_resources'] = {'target_cpus': 8, 'target_memory_bytes': 16 * GiB,
                                    'load_cpus': client_cpus, 'load_memory_bytes': client_memory}
    initial = read(root / 'target-initial.json')
    pg = setting_map(initial)
    check(checks, 'durable_fixed_postgres18', pg.get('server_version_num', ('',))[0].startswith('18')
          and pg.get('max_connections', ('',))[0] == '100'
          and all(pg.get(k, ('',))[0] == 'on' for k in ['fsync', 'synchronous_commit', 'full_page_writes']))
    for kind, cpus, memory in [('target', 8, 16 * GiB), ('load', client_cpus, client_memory)]:
        before, after = read(root / (kind + '-inspect.json')), read(root / (kind + '-final-inspect.json'))
        check(checks, kind + ':actual_budget_identity_and_no_affinity', bool(before) and bool(after)
              and inspect_budget(before, cpus, memory) and inspect_budget(after, cpus, memory)
              and before['Id'] == after['Id'])
        if kind == 'load':
            check(checks, 'load:container_GOMAXPROCS2_before_and_after', all(
                  [v for v in inspection.get('Config', {}).get('Env', []) if v.startswith('GOMAXPROCS=')] == ['GOMAXPROCS=2']
                  for inspection in [before, after]))
    target, load = read(root / 'target-inspect.json'), read(root / 'load-inspect.json')
    check(checks, 'external_client_cgroup_shared_network_only', target['Id'] != load['Id']
          and load['HostConfig']['NetworkMode'] == 'container:' + target['Id'])
    tools = read(root / 'tool-sha256.json', {})
    check(checks, 'all_run_tools_frozen', bool(tools) and all((root / 'tools' / name).exists()
          and sha(root / 'tools' / name) == value for name, value in tools.items()))
    expected_native = plan['configuration'].get('expected_native_sha256')
    native = (root / 'native-sha256.txt').read_text().split()[0] if (root / 'native-sha256.txt').exists() else None
    check(checks, 'native_binary_matches_pinned_hash', bool(expected_native) and native == expected_native)
    seed_log = Path(plan['configuration']['old_host_evidence']) / 'seed-full.log'
    seed_setup = Path(plan['configuration']['old_host_evidence']) / 'setup/upstream-sha256.txt'
    check(checks, 'original_full_seed_fingerprint_validated', seed_log.exists()
          and 'OK: conduit_seed matches the reference seed' in seed_log.read_text()
          and seed_setup.exists() and initial['official_source_sha256']['seed/make-seed.sh'] + '  /work/seed/make-seed.sh' in seed_setup.read_text())
    check(checks, 'final_resource_check_valid', read(root / 'final-resource-check.json', {}).get('valid') is True)
    global_ok = all(c['pass'] for c in checks)
    result['study_complete'] = all(e.get('error') is None for e in events if e['event'] == 'controller_finished')
    for case in plan['configuration']['cases']:
        directory = root / 'cases' / case['name']
        row = {'case': case['name'], 'checks': [], 'phases': [], 'capacity_users': None,
               'selected_users': case['confirm_users'], 'confirmed_users': None, 'confirmation_passed': False,
               'capacity_maximum_established': False,
               'source_revision': case.get('source_revision'), 'binary_sha256': case['expected_binary_sha256']}
        if not directory.exists():
            row['status'] = 'NOT_STARTED'
            result['rows'].append(row)
            continue
        cc = row['checks']
        metadata = read(directory / 'frozen/metadata.json', {})
        app, db = read(directory / 'app.json', {}), read(directory / 'database.json', {})
        source = directory / 'frozen/source'
        actual_sources = {str(p.relative_to(source)): sha(p) for p in source.rglob('*') if p.is_file()} if source.exists() else {}
        check(cc, 'source_archive_and_manifest_frozen', actual_sources == metadata.get('source_sha256')
              and hashlib.sha256(json.dumps(actual_sources, sort_keys=True).encode()).hexdigest() == metadata.get('source_manifest_sha256'))
        check(cc, 'exact_predeclared_case_and_binary', metadata.get('case') == case
              and (directory / 'frozen/app').exists()
              and sha(directory / 'frozen/app') == metadata.get('binary_sha256') == case['expected_binary_sha256'])
        check(cc, 'owned_app_stopped', bool(app) and read(directory / 'stopped.json', {}).get('stopped_pgid') == app.get('pgid'))
        check(cc, 'owned_fresh_database_dropped', bool(db)
              and read(directory / 'dropped.json', {}) == {'database': db.get('database'), 'dropped': True})
        row['conformance_197_full_seed_proven'] = conformance(directory, case)
        phases = sorted((directory / 'phases').iterdir()) if (directory / 'phases').exists() else []
        phases = [p for p in phases if p.is_dir()]
        replay = []
        actions = confirmation_actions(case)
        for index, phase_dir in enumerate(phases):
            state = read(phase_dir / 'phase.json', {})
            action = actions[index] if index < len(actions) else None
            check(cc, phase_dir.name + ':predeclared_fixed_confirmation_action', action is not None
                  and action.get('stage') == state.get('stage') and action.get('users') == state.get('users'))
            check(cc, phase_dir.name + ':no_phase_after_failure_or_invalidity',
                  all(p.get('classification') == 'PASS' and p.get('eligible') is True for p in replay))
            phase = audit_phase(phase_dir, directory, plan, case, initial, global_ok and all(c['pass'] for c in cc))
            row['phases'].append(phase)
            replay.append(phase)
        recorded_starts = [e['id'] for e in events if e['event'] == 'phase_start' and e['case'] == case['name']]
        check(cc, 'all_started_phases_preserved_once', recorded_starts == [p.name for p in phases]
              and len(recorded_starts) == len(set(recorded_starts)))
        qualified = global_ok and all(c['pass'] for c in cc) and row['conformance_197_full_seed_proven']
        passed = len(replay) == 3 and all(p.get('classification') == 'PASS' and p.get('eligible') is True for p in replay)
        if qualified and passed:
            held = replay[-1]
            row.update(confirmed_users=case['confirm_users'], confirmation_passed=True,
                       status='LOCAL_CONFIRMATION_PASSED', held_phase=held['id'], measured_seconds=300,
                       overall=held['overall'], zero_measured_errors=held['zero_measured_errors'],
                       observed_timeline_errors=held['observed_timeline_errors'],
                       cpu_ms_per_successful_request_sampled_estimate=held['cpu_ms_per_successful_request_sampled_estimate'],
                       native_qualified=held['native_qualified'], local_qualified=held['local_qualified'],
                       native_verdict=held['native_verdict'],
                       native_whole_vm_CPU_flag_count=held['native_whole_vm_CPU_flag_count'],
                       native_whole_vm_CPU_flagged_shards=held['native_whole_vm_CPU_flagged_shards'],
                       local_whole_vm_CPU_scope_exception=held['local_whole_vm_CPU_scope_exception'])
        else:
            last = replay[-1]['classification'] if replay else read(directory / 'session.json', {}).get('status', 'INCOMPLETE')
            row['status'] = 'UNQUALIFIED_CONFORMANCE' if passed and not row['conformance_197_full_seed_proven'] else 'CONFIRMATION_STOP_' + last
        result['rows'].append(row)
    result['status'] = 'AUDITED_COMPLETED_CONFIRMATION' if global_ok else 'INVALID_GLOBAL_EVIDENCE'
    result['both_selected_points_confirmed'] = len(result['rows']) == 2 and all(r.get('confirmation_passed') for r in result['rows'])
    result['interpretation'] = ('This fresh reverse-order block confirms only its preselected held-user points when warmup, probe and300s hold all qualify. '
                                'It does not search for or establish a new maximum or failure bound; prior first-study bounds remain separate. '
                                'Any invalidity or SLO failure stops that case without fallback, retry or phase reuse. '
                                'Native flags and exact measured/ramp/tail errors remain visible. No official x86 rank or controlled causal claim is made.')
    if cpu_scope == 'dedicated_client_cgroup_v1':
        result['interpretation'] += (' The unchanged preregistered local policy substitutes external-client cgroup CPU<=75% for native whole-VM CPU only. '
                                     'All timing/active/clock/histogram/error/SLO gates remain; local confirmation can remain native LG-limited.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit_run(args.run)
    result['created_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    result['auditor_sha256'] = {str(p.name): sha(p) for p in [Path(__file__), Path(__file__).with_name('evidence.py'), Path(__file__).with_name('primitives.py')]}
    if result['status'] != 'ACTIVE_NOT_READ':
        result['raw_input_sha256'] = {str(p.relative_to(args.run)): sha(p) for p in args.run.rglob('*') if p.is_file()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    lines = ['# Selected-point confirmation audit', '', result['scope'], '',
             'Qualification follows the preregistered `' + str(result.get('client_cpu_scope_policy')) + '` policy. Local and native qualification of each scored hold are shown separately.', '',
             '| Implementation | Result | Selected users | Confirmed300s users | p95/p99 ms | Measured errors | Local qualified | Native qualified | Whole-VM CPU flags |',
             '|---|---|---:|---:|---:|---:|---|---|---:|']
    for r in result['rows']:
        m = r.get('overall', {})
        lines.append(f"| {r['case']} | {r['status']} | {r.get('selected_users') or '—'} | {r.get('confirmed_users') or '—'} | {str(m.get('p95_ms', '—')) + '/' + str(m.get('p99_ms', '—'))} | {m.get('errors', '—')} | {r.get('local_qualified', '—')} | {r.get('native_qualified', '—')} | {r.get('native_whole_vm_CPU_flag_count', '—')} |")
    lines.extend(['', result.get('interpretation', 'Active run; no raw phases audited.')])
    args.out.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'output': str(args.out), 'status': result['status'], 'rows': [{k: r.get(k) for k in ['case', 'status', 'selected_users', 'confirmed_users']} for r in result['rows']]}))


if __name__ == '__main__':
    main()
