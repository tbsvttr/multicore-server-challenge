#!/usr/bin/env python3
"""Audit completed capacity searches from raw artifacts; never runs Docker."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from search_policy import DEFAULT_PROTOCOL, client_cpu_scope_policy, growth_factor, load_cpus, load_memory_bytes, next_action
from audit.evidence import audit_phase, conformance
from audit.primitives import GiB, check, inspect_budget, jsonl, read, setting_map, sha


def audit_run(root):
    plan, events = read(root / 'plan.json'), jsonl(root / 'events.jsonl')
    result = {'run': str(root), 'checks': [], 'rows': [], 'official_rank_proven': False,
              'all_competitors_beaten': False, 'scope': plan['scope']}
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
    try:
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
               'highest_passing_probe_users': None, 'highest_passing_hold_users': None,
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
        for phase_dir in phases:
            state = read(phase_dir / 'phase.json', {})
            action = next_action(replay, plan['protocol'])
            check(cc, phase_dir.name + ':predeclared_search_decision', action['stage'] != 'stop'
                  and action.get('stage') == state.get('stage') and action.get('users') == state.get('users'))
            phase = audit_phase(phase_dir, directory, plan, case, initial, global_ok and all(c['pass'] for c in cc))
            row['phases'].append(phase)
            replay.append(phase)
        recorded_starts = [e['id'] for e in events if e['event'] == 'phase_start' and e['case'] == case['name']]
        check(cc, 'all_started_phases_preserved_once', recorded_starts == [p.name for p in phases]
              and len(recorded_starts) == len(set(recorded_starts)))
        passing_probes = [p for p in replay if p['stage'] == 'probe' and p['eligible']]
        passing_holds = [p for p in replay if p['stage'] == 'hold' and p['eligible']]
        row['highest_passing_probe_users'] = max((p['users'] for p in passing_probes), default=None)
        row['highest_passing_hold_users'] = max((p['users'] for p in passing_holds), default=None)
        qualified = global_ok and all(c['pass'] for c in cc) and row['conformance_197_full_seed_proven']
        if qualified and passing_holds:
            best = max(passing_holds, key=lambda p: p['users'])
            upper = min((p['users'] for p in replay if p.get('valid_server_failure') and p['users'] > best['users']), default=None)
            resolved = upper is not None and upper - best['users'] <= plan['protocol']['resolution'] * best['users']
            row.update(capacity_users=best['users'], scored_phase=best['id'], measured_seconds=300,
                       failed_upper_bound_users=upper,
                       status='LOCAL_CAPACITY_INTERVAL' if resolved else 'LOCAL_HOLD_LOWER_BOUND',
                       capacity_interval={'held_at_least_users': best['users'], 'failed_at_users': upper},
                       overall=best['overall'], zero_measured_errors=best['zero_measured_errors'],
                       observed_timeline_errors=best['observed_timeline_errors'],
                       cpu_ms_per_successful_request_sampled_estimate=best['cpu_ms_per_successful_request_sampled_estimate'])
            row.update(native_qualified=best['native_qualified'], local_qualified=best['local_qualified'],
                       native_verdict=best['native_verdict'],
                       native_whole_vm_CPU_flag_count=best['native_whole_vm_CPU_flag_count'],
                       native_whole_vm_CPU_flagged_shards=best['native_whole_vm_CPU_flagged_shards'],
                       local_whole_vm_CPU_scope_exception=best['local_whole_vm_CPU_scope_exception'])
        else:
            last = replay[-1]['classification'] if replay else read(directory / 'session.json', {}).get('status', 'INCOMPLETE')
            row['status'] = 'UNQUALIFIED_CONFORMANCE' if passing_holds and not row['conformance_197_full_seed_proven'] else last if last != 'PASS' else 'NO_PASSING_HOLD'
        result['rows'].append(row)
    result['status'] = 'AUDITED_COMPLETED_LOCAL_SEARCH' if global_ok else 'INVALID_GLOBAL_EVIDENCE'
    result['interpretation'] = ('Only a qualified300s hold yields a local held-user score. Ceiling/budget bounds are censored lower bounds, '
                                'not proved maxima. Invalid generator/clock phases never become server failures or capacity scores. '
                                'Native SLO permits<1% measured errors; zero errors and recorded ramp/tail errors are separate. '
                                'This ARM Mac study cannot establish the official x86 leaderboard rank.')
    if cpu_scope == 'dedicated_client_cgroup_v1':
        result['interpretation'] += (' Preregistered local qualification substitutes measured external-client cgroup CPU≤75% '
                                     'for the native whole-VM /proc/stat CPU flag only. All native timing/active-user gates remain. '
                                     'Native verdicts are preserved separately; a local score may remain native LG-limited and is not an official/native-qualified score.')
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
    lines = ['# Local capacity audit', '', result['scope'], '',
             'Qualification follows the preregistered `' + str(result.get('client_cpu_scope_policy')) + '` policy. Local and native qualification of each scored hold are shown separately.', '',
             '| Implementation | Result |300s held users | Highest60s probe | p95/p99 ms | Measured errors | Local qualified | Native qualified | Whole-VM CPU flags |',
             '|---|---|---:|---:|---:|---:|---|---|---:|']
    for r in result['rows']:
        m = r.get('overall', {})
        lines.append(f"| {r['case']} | {r['status']} | {r.get('capacity_users') or '—'} | {r.get('highest_passing_probe_users') or '—'} | {str(m.get('p95_ms', '—')) + '/' + str(m.get('p99_ms', '—'))} | {m.get('errors', '—')} | {r.get('local_qualified', '—')} | {r.get('native_qualified', '—')} | {r.get('native_whole_vm_CPU_flag_count', '—')} |")
    lines.extend(['', result.get('interpretation', 'Active run; no raw phases audited.')])
    args.out.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'output': str(args.out), 'status': result['status'], 'rows': [{k: r.get(k) for k in ['case', 'status', 'capacity_users', 'highest_passing_probe_users']} for r in result['rows']]}))


if __name__ == '__main__':
    main()
