#!/usr/bin/env python3
"""Evaluate the frozen W2/ARTICLE1 contract after a completed independent audit.

The primary CPU metric exactly follows the preregistered sampled inner interval.
The separate full-window interpolated metric remains available for comparison.
No Docker, network, target request, or mutation of raw evidence is performed.
"""
import argparse
import json
from pathlib import Path
import time

from analyze_paired import jsonl, read, sha


def cpu_per_success(directory, native):
    meta = read(directory / 'box0.json')['meta']
    rows = [r for r in jsonl(directory / 'target-monitor.jsonl')
            if meta['window_start_ms'] <= r['wall_ns'] / 1e6 <= meta['window_end_ms']]
    if len(rows) < 2: return None
    first, last = rows[0], rows[-1]
    seconds = (last['monotonic_ns'] - first['monotonic_ns']) / 1e9
    cpu_seconds = (last['cpu']['usage_usec'] - first['cpu']['usage_usec']) / 1e6
    successful_rps = (native['count'] - native['errors']) / 60
    if seconds <= 0 or cpu_seconds < 0 or successful_rps <= 0: return None
    return {'cpu_seconds_per_successful_request': cpu_seconds / seconds / successful_rps,
            'sampled_interval_s': seconds,
            'sampled_interval_start_ms': first['wall_ns'] / 1e6,
            'sampled_interval_end_ms': last['wall_ns'] / 1e6,
            'cpu_seconds': cpu_seconds, 'successful_rps': successful_rps,
            'scope': 'Combined8CPU app+PostgreSQL target cgroup; sampled inner interval.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--audit', type=Path, default=Path('/private/tmp/multicore-research-20261022/audit/multi-audit.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    plan = read(args.run / 'plan.json')
    contract = plan['preregistered_acceptance']
    full_audit = read(args.audit)
    audited = next(r for r in full_audit['runs'] if Path(r['run']).resolve() == args.run.resolve())
    cases = [case['name'] for case in plan['configuration']['cases']]
    attempts = audited['attempts']
    initial_checks = {
        'independent_run_evidence_passes': audited['status'] == 'PASS_LOCAL_EVIDENCE',
        'all_six_scheduled_attempts_present': len(attempts) == 6 and not audited.get('planned_but_not_started'),
        'all_three_pairs_clean': len(audited['pairs']) == 3 and all(pair['qualified'] for pair in audited['pairs']),
        'zero_errors_all_recorded_windows': all(a.get('zero_observed_errors') is True for a in attempts),
        'frozen_plan_hash_matches': sha(args.run / 'plan.json') == (args.run / 'plan.sha256').read_text().strip(),
    }
    results = []
    for pair in range(1, 4):
        members = {a['case']: a for a in attempts if a['pair'] == pair}
        checks = {'both_declared_arms_present': set(members) == set(cases)}
        result = {'pair': pair, 'checks': checks}
        if checks['both_declared_arms_present']:
            reference, candidate = (members[name] for name in cases)
            measured = {}
            for arm in [reference, candidate]:
                directory = args.run / arm['id']
                measured[arm['case']] = cpu_per_success(directory, arm['overall']) if 'overall' in arm else None
                raw = [read(directory / f'box{i}.json', {}) for i in range(4)]
                checks[arm['case'] + '_all80000_vus_active'] = all(r.get('box', {}).get('active_vus_at_window_start') == 20000 for r in raw)
                checks[arm['case'] + '_clean_and_eligible'] = arm.get('eligible') is True and arm.get('zero_observed_errors') is True
            result['preregistered_cpu_measurements'] = measured
            aa, bb = (measured[name] for name in cases)
            if aa and bb:
                ratio = bb['cpu_seconds_per_successful_request'] / aa['cpu_seconds_per_successful_request']
                result.update(cpu_ratio_candidate_over_reference=ratio, cpu_improvement_fraction=1 - ratio)
                checks['combined_cpu_per_success_at_least5pct_lower'] = ratio <= .95
            else:
                checks['combined_cpu_per_success_at_least5pct_lower'] = False
            cm, rm = candidate.get('overall', {}), reference.get('overall', {})
            checks['p95_no_regression'] = 'p95_ms' in cm and 'p95_ms' in rm and cm['p95_ms'] <= rm['p95_ms']
            checks['p99_no_regression'] = 'p99_ms' in cm and 'p99_ms' in rm and cm['p99_ms'] <= rm['p99_ms']
            result['full_window_interpolated_cpu_ratio'] = next((p.get('ratios_candidate_over_reference', {}).get('total_cpu_ms_per_successful_request_estimate')
                                                               for p in audited['pairs'] if p['pair'] == pair), None)
        result['pass'] = all(checks.values())
        results.append(result)
    output = {'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'run': str(args.run.resolve()),
              'evaluator_sha256': sha(Path(__file__)), 'independent_audit_sha256': sha(args.audit),
              'frozen_plan_sha256': sha(args.run / 'plan.json'), 'contract': contract,
              'initial_checks': initial_checks, 'pairs': results,
              'accepted': all(initial_checks.values()) and len(results) == 3 and all(r['pass'] for r in results),
              'official_capacity_or_rank_proven': False,
              'interpretation': 'Only the predeclared local combined-configuration CPU/latency contract is evaluated. Equal fixed-load RPS, maximum users, and official rank are different questions.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'output': str(args.out), 'accepted': output['accepted'], 'initial_checks': initial_checks,
                      'pairs': [{'pair': p['pair'], 'pass': p['pass'], 'cpu_improvement_fraction': p.get('cpu_improvement_fraction')} for p in results]}))


if __name__ == '__main__': main()
