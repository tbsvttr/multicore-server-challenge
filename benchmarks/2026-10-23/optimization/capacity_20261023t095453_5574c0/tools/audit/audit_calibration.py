#!/usr/bin/env python3
"""Audit a completed five-arm fixed80k calibration; never invokes Docker."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

OLD = Path('/private/tmp/multicore-research-20261022/audit')
sys.path.insert(0, str(OLD))
import analyze_multi as auditor
from analyze_paired import GiB, check, inspect_budget, jsonl, read, setting_map, sha
from evaluate_preregistered import cpu_per_success


def audit(root):
    plan, events = read(root / 'plan.json'), jsonl(root / 'events.jsonl')
    output = {'run': str(root), 'scope': plan['scope'], 'checks': [], 'arms': [],
              'capacity_or_rank_proven': False, 'stable_gain_proven': False}
    checks = output['checks']
    if not any(e['event'] == 'controller_finished' for e in events):
        output['status'] = 'ACTIVE_NOT_READ'
        return output
    cfg, protocol = plan['configuration'], plan['protocol']
    check(checks, 'exact_declared_five_arm_exploratory_block', plan.get('diagnostic_only') is True
          and protocol['order'] == [[0, 1, 2, 3, 4]] and len(cfg['cases']) == 5
          and plan['selection_policy']['calibration_is_not_confirmation'] is True)
    check(checks, 'frozen_plan_hash', sha(root / 'plan.json') == (root / 'plan.sha256').read_text().strip())
    config_path = Path(plan['configuration_file'])
    check(checks, 'actual_configuration_file_hash_and_contents', config_path.exists()
          and sha(config_path) == plan['configuration_sha256'] and read(config_path) == cfg)
    created = datetime.datetime.fromisoformat(plan['created_utc'].replace('Z', '+00:00'))
    check(checks, 'current_plan_timestamp_precedes_first_event', created.tzinfo is not None
          and created.timestamp() * 1e9 <= min(e['wall_ns'] for e in events))
    names = [c['name'] for c in cfg['cases']]
    expected = [f'{i + 1:02d}-p1-{name}' for i, name in enumerate(names)]
    check(checks, 'all_declared_arms_retained_once_without_replacement',
          [e['id'] for e in events if e['event'] == 'attempt_start'] == expected
          and [e['id'] for e in events if e['event'] == 'attempt_complete'] == expected
          and sorted(p.name for p in root.iterdir() if p.is_dir() and p.name[:2].isdigit()) == expected)
    check(checks, 'controller_completed_cleanly', not any(e['event'] == 'controller_error' for e in events)
          and all(e.get('error') is None for e in events if e['event'] == 'controller_finished'))
    initial = read(root / 'target-initial.json')
    for kind, cpus, memory in [('target', 8, 16 * GiB), ('load', 4, 4 * GiB)]:
        before, after = read(root / (kind + '-inspect.json')), read(root / (kind + '-final-inspect.json'))
        check(checks, kind + ':fixed_budgets_identity_no_affinity', inspect_budget(before, cpus, memory)
              and inspect_budget(after, cpus, memory) and before['Id'] == after['Id'])
    target, load = read(root / 'target-inspect.json'), read(root / 'load-inspect.json')
    check(checks, 'separate_client_cgroup_shared_network', target['Id'] != load['Id']
          and load['HostConfig']['NetworkMode'] == 'container:' + target['Id'])
    pg = setting_map(initial)
    check(checks, 'durable_postgres18', pg['server_version_num'][0].startswith('18') and pg['max_connections'][0] == '100'
          and all(pg[k][0] == 'on' for k in ['fsync', 'synchronous_commit', 'full_page_writes']))
    check(checks, 'final_resource_witness_valid', read(root / 'final-resource-check.json')['valid'] is True)
    frozen = {}
    for case in cfg['cases']:
        directory = root / 'frozen' / case['name']; meta = read(directory / 'metadata.json'); frozen[case['name']] = meta
        source = {str(p.relative_to(directory / 'source')): sha(p) for p in (directory / 'source').rglob('*') if p.is_file()}
        check(checks, case['name'] + ':actual_binary_and_source_frozen', meta['case'] == case
              and sha(directory / 'app') == meta['binary_sha256'] == case['expected_binary_sha256']
              and source == meta['source_sha256']
              and hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest() == meta['source_manifest_sha256'])
    tools = read(root / 'frozen-tool-sha256.json')
    check(checks, 'executed_tools_frozen', all(sha(root / 'tools' / n) == value for n, value in tools.items()))
    check(checks, 'native_generator_pinned', read(root / 'tool-source-sha256.json')['tools/loadgen']
          == '886eaa564c6cdab1a791534d6931d1b8eb9b5c21d1e1ebaaa2824616c4562cdb')
    research = root.parent.parent
    check(checks, 'full_seed_template_fingerprint_validated',
          'OK: conduit_seed matches the reference seed' in (research / 'seed-full.log').read_text()
          and initial['official_source_sha256']['seed/make-seed.sh'] + '  /work/seed/make-seed.sh' in (research / 'setup/upstream-sha256.txt').read_text())
    global_ok = all(c['pass'] for c in checks)
    for name, case in zip(expected, cfg['cases']):
        result = auditor.assess_attempt(root / name, plan, initial, frozen, global_ok)
        result['effective_env'] = case['env']
        result['frozen_binary_sha256'] = frozen[case['name']]['binary_sha256']
        result['frozen_source_manifest_sha256'] = frozen[case['name']]['source_manifest_sha256']
        result['sampled_inner_cpu'] = cpu_per_success(root / name, result['overall']) if result.get('overall') else None
        result['zero_error_selection_eligible'] = result['eligible'] and result.get('zero_observed_errors') is True
        result['largest_endpoint_p99_ms'] = [{k: e.get(k) for k in ['name', 'count', 'p95_ms', 'p99_ms', 'errors']}
                                             for e in sorted(result.get('endpoints') or [], key=lambda e: e['p99_ms'], reverse=True)[:5]]
        output['arms'].append(result)
    same_stream = len({a.get('raw_run_id') for a in output['arms']}) == 1
    check(checks, 'common_native_run_id_across_all_five_arms', same_stream)
    control = output['arms'][0]
    for result in output['arms']:
        result['contrast_vs_rust'] = {}
        for key in ['rps', 'p50_ms', 'p95_ms', 'p99_ms', 'total_cpu_ms_per_successful_request_estimate', 'app_cpu_ms_per_successful_request_estimate']:
            left, right = result.get('metrics', {}).get(key), control.get('metrics', {}).get(key)
            if left is not None and right:
                result['contrast_vs_rust'][key] = {'ratio': left / right, 'change_pct': (left / right - 1) * 100}
        if result['sampled_inner_cpu'] and control['sampled_inner_cpu']:
            ratio = result['sampled_inner_cpu']['cpu_seconds_per_successful_request'] / control['sampled_inner_cpu']['cpu_seconds_per_successful_request']
            result['contrast_vs_rust']['sampled_inner_cpu_per_success'] = {'ratio': ratio, 'change_pct': (ratio - 1) * 100}
    clean = all(a['zero_error_selection_eligible'] for a in output['arms']) and all(c['pass'] for c in checks)
    candidates = output['arms'][1:]
    selected_full = min(candidates, key=lambda a: a['metrics']['total_cpu_ms_per_successful_request_estimate']) if clean else None
    selected_inner = min(candidates, key=lambda a: a['sampled_inner_cpu']['cpu_seconds_per_successful_request']) if clean else None
    output['selection'] = {'eligible_all_five_arms': clean,
        'minimum_full_window_cpu_candidate': selected_full['case'] if selected_full else None,
        'minimum_sampled_inner_cpu_candidate': selected_inner['case'] if selected_inner else None,
        'both_cpu_estimates_agree': bool(selected_full and selected_inner and selected_full['case'] == selected_inner['case']),
        'selected_case': selected_full['case'] if selected_full and selected_inner and selected_full['case'] == selected_inner['case'] else None,
        'purpose': 'Choose a configuration for independent warmup/search/300s capacity testing; no promotion or capacity/rank proof.',
        'repeats': 1,
        'new_correctness_binary_limit': 'Calibration metrics belong to the frozen a34 candidate. Any later correctness fixes create a new binary requiring its own validation and capacity run; these metrics are not silently transferred.'}
    if output['selection']['selected_case']:
        chosen = next(a for a in output['arms'] if a['case'] == output['selection']['selected_case'])
        output['selection'].update(env=chosen['effective_env'], calibration_binary_sha256=chosen['frozen_binary_sha256'],
                                   whole_target_cpu_cost_ms_per_success=chosen['metrics']['total_cpu_ms_per_successful_request_estimate'])
    host = jsonl(root / 'host-memory.jsonl')
    offsets = [(r['wall_ns'] - r['monotonic_ns']) / 1e9 for r in host]
    output['host_diagnostics'] = {'samples': len(host), 'clock_offset_range_s': max(offsets) - min(offsets) if offsets else None,
                                  'scope': 'Shared-host observations are diagnostic; no retrospective exclusions.'}
    output['status'] = 'PASS_EXPLORATORY_CALIBRATION' if clean and same_stream else 'HAS_INVALID_OR_ERRORFUL_ARMS'
    output['interpretation'] = 'Each arm is one fixed-load run. CPU and latency contrasts are descriptive; similar closed-model request rates cannot establish sustainable capacity. No extra grid or selective reruns are authorized by this audit.'
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run)
    result['created_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    result['auditor_sha256'] = {'audit_calibration.py': sha(Path(__file__)), 'analyze_multi.py': sha(OLD / 'analyze_multi.py'),
                               'analyze_paired.py': sha(OLD / 'analyze_paired.py'), 'evaluate_preregistered.py': sha(OLD / 'evaluate_preregistered.py')}
    if result['status'] != 'ACTIVE_NOT_READ':
        result['raw_input_sha256'] = {str(p.relative_to(args.run)): sha(p) for p in args.run.rglob('*') if p.is_file()}
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    lines = ['# Five-arm80k calibration audit', '', result['status'], '',
             '| Arm | Result | Req/s | p50/p95/p99 ms | CPU ms/success, full window | CPU ms/success, sampled inner | Errors |',
             '|---|---|---:|---:|---:|---:|---:|']
    for arm in result['arms']:
        m = arm['metrics']; inner = arm['sampled_inner_cpu']
        lines.append(f"| {arm['case']} | {arm['classification']} | {m['rps']:.2f} | {m['p50_ms']:.3f}/{m['p95_ms']:.3f}/{m['p99_ms']:.3f} | {m['total_cpu_ms_per_successful_request_estimate']:.6f} | {inner['cpu_seconds_per_successful_request'] * 1000:.6f} | {m['errors']} |")
    lines.extend(['', 'Selection: ' + str(result.get('selection', {}).get('selected_case')), '', result.get('interpretation', 'Active study; no raw audit.')])
    args.out.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    args.out.with_name('calibration-selection.json').write_text(json.dumps(result.get('selection', {}), indent=2) + '\n')
    print(json.dumps({'output': str(args.out), 'status': result['status'], 'global_failed': [c for c in result['checks'] if not c['pass']],
                      'arms': [{'case': a['case'], 'classification': a['classification'], 'rps': a['metrics']['rps'],
                                'cpu_ms_per_success_full': a['metrics']['total_cpu_ms_per_successful_request_estimate'],
                                'cpu_ms_per_success_inner': a['sampled_inner_cpu']['cpu_seconds_per_successful_request'] * 1000} for a in result['arms']],
                      'selection': result.get('selection')}))


if __name__ == '__main__':
    main()
