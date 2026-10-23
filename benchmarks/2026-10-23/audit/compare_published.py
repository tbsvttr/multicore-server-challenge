#!/usr/bin/env python3
"""Audit the pinned maintainer leaderboard and submission coverage, read-only.

This verifies published table contents and arithmetic. It does not re-audit the
unpublished raw benchmark trials or infer which source revision was measured.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_table(text):
    scored, unscored = [], []
    not_scored = False
    for line in text.splitlines():
        if line.startswith('## Not scored'):
            not_scored = True
        if not line.startswith('| '):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if not not_scored and cells and cells[0].isdigit():
            if len(cells) != 10:
                raise ValueError('unexpected scored row: ' + line)
            rank, users, submission, pr, front, rps, p95, p99, cpu, note = cells
            name, link = re.search(r'\[([^]]+)\]\(([^)]+)\)', submission).groups()
            pr_number = int(re.search(r'\[#(\d+)\]', pr)[1]) if '[#' in pr else None
            cpu_values = [int(n) for n in re.findall(r'(\d+)%', cpu)]
            scored.append({
                'id': 'pr-' + str(pr_number) if pr_number else link.replace('/', '-'),
                'published_rank': int(rank), 'users': int(users.replace('*', '').replace(',', '')),
                'submission': name, 'submission_link': link, 'pr': pr_number,
                'front': front, 'rps': int(rps.replace(',', '')), 'p95_ms': int(p95), 'p99_ms': int(p99),
                'app_cpu_pct_of_whole8cpu_box': cpu_values[0],
                'postgres_cpu_pct_of_whole8cpu_box': cpu_values[1],
                'nginx_cpu_pct_of_whole8cpu_box': cpu_values[2] if len(cpu_values) > 2 else 0,
                'cpu_values_are_rounded_published_percentages': True,
                'status': 'OFFICIAL_SCORED_WITH_NOTE' if note else 'OFFICIAL_SCORED',
                'maintainer_note': note, 'measured_error_count': None, 'zero_errors_proven': False,
                'measured_source_commit': None, 'measured_source_version_proven': False,
                'raw_trials_independently_audited': False,
            })
        elif not_scored and cells and re.search(r'\[#\d+\]', cells[1] if len(cells) > 1 else ''):
            if len(cells) != 3:
                raise ValueError('unexpected unscored row: ' + line)
            submission, pr, why = cells
            name, link = re.search(r'\[([^]]+)\]\(([^)]+)\)', submission).groups()
            unscored.append({'id': 'pr-' + re.search(r'\[#(\d+)\]', pr)[1], 'pr': int(re.search(r'\[#(\d+)\]', pr)[1]),
                             'submission': name, 'submission_link': link, 'status': 'OFFICIAL_NOT_SCORED',
                             'users': None, 'published_rank': None, 'maintainer_note': why,
                             'raw_trials_independently_audited': False, 'measured_source_version_proven': False})
    return scored, unscored


def compare(inventory, canonical_path, current_path):
    text_bytes = (inventory / 'LEADERBOARD.md').read_bytes()
    text = text_bytes.decode('utf-8')
    commit = json.loads((inventory / 'main-commit-raw.json').read_text())
    tree = json.loads((inventory / 'main-actual-tree-raw.json').read_text())
    canonical = json.loads(canonical_path.read_text())
    current = json.loads(current_path.read_text())
    pulls = {p['number']: p for p in json.loads((inventory / 'pulls-raw.json').read_text())}
    heads = {p['pr']: p for p in json.loads((inventory / 'head-source-manifest.json').read_text())['entries']}
    entry = next(p for p in tree['tree'] if p['path'] == 'LEADERBOARD.md')
    blob = hashlib.sha1(b'blob ' + str(len(text_bytes)).encode() + b'\0' + text_bytes).hexdigest()
    scored, unscored = parse_table(text)
    seen_prs = {r['pr'] for r in scored + unscored if r['pr'] is not None}
    scored_prs = {r['pr'] for r in scored if r['pr'] is not None}
    merged_prs = {n for n, p in pulls.items() if p.get('merged_at')}
    checks = []

    def check(name, passed, detail=None):
        checks.append({'check': name, 'pass': bool(passed), **({'detail': detail} if detail is not None else {})})

    check('pinned_commit_matches_canonical_url', '/blob/' + commit['sha'] + '/LEADERBOARD.md' in canonical['url'])
    check('actual_git_tree_matches_commit_tree', tree['sha'] == commit['commit']['tree']['sha'] and tree.get('truncated') is False)
    check('local_leaderboard_git_blob_matches_canonical_tree', blob == entry['sha'] and len(text_bytes) == entry['size'])
    check('local_text_identical_to_fresh_pinned_github_content', text == canonical['content'])
    check('current_main_github_content_identical_to_pinned_snapshot', text == current['content'])
    check('29_scored_rows_and_two_unscored', len(scored) == 29 and len(unscored) == 2)
    check('published_ranks_contiguous_and_preserved', [r['published_rank'] for r in scored] == list(range(1, 30)))
    check('scores_nonincreasing_preserving_tie_order', all(a['users'] >= b['users'] for a, b in zip(scored, scored[1:])))
    check('one_official_row_per_submission', len({r['id'] for r in scored + unscored}) == len(scored + unscored)
          and len({r['submission'] for r in scored + unscored}) == len(scored + unscored))
    check('all_published_prs_present_in_fresh_inventory', seen_prs <= set(pulls) and seen_prs <= set(heads))
    check('all_merged_submission_prs_have_published_scores', merged_prs <= scored_prs, sorted(merged_prs - scored_prs))
    check('all_published_latency_values_meet_declared_slo', all(r['p95_ms'] < 500 and r['p99_ms'] < 1000 for r in scored))
    check('four_examples_included_on_same_box', len([r for r in scored if r['pr'] is None]) == 4)
    own = next(r for r in scored if r['pr'] == 32)
    leader = scored[0]
    reference = next(r for r in scored if r['pr'] == 31)
    check('our_published_row_is_65000_users_at_rank8', own['users'] == 65000 and own['published_rank'] == 8)
    check('leader_is_rust7_at100000', leader['pr'] == 7 and leader['users'] == 100000)
    gaps = []
    for number in sorted(set(heads) - seen_prs):
        p, head = pulls[number], heads[number]
        gaps.append({'pr': number, 'submission': head['folder'], 'current_head': head['head'],
                     'pull_request_state': p['state'], 'merged_at': p.get('merged_at'),
                     'status': 'NOT_LISTED_OPEN_SUBMISSION' if p['state'] == 'open' else 'NOT_LISTED_CLOSED_UNMERGED_PROPOSAL',
                     'users': None, 'published_rank': None,
                     'reason': 'No separate result or failure reason for this PR is published in the pinned leaderboard. Do not copy a score from a similarly named folder or successor PR.'})
    for r in scored + unscored:
        if r['pr']:
            p, head = pulls[r['pr']], heads[r['pr']]
            r.update(current_head=head['head'], current_head_is_measured_revision_proven=False,
                     current_pr_state=p['state'], currently_merged=p.get('merged_at') is not None,
                     current_draft=p.get('draft', False))
    ties = collections.defaultdict(list)
    for r in scored:
        ties[r['users']].append(r['published_rank'])
    inputs = [inventory / n for n in ['LEADERBOARD.md', 'README.md', 'WORKLOAD.md', 'main-commit-raw.json',
              'main-actual-tree-raw.json', 'pulls-raw.json', 'head-source-manifest.json']] + [canonical_path, current_path]
    return {
        'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'status': 'PASS_PUBLISHED_TABLE_AUDIT' if all(c['pass'] for c in checks) else 'FAIL_PUBLISHED_TABLE_AUDIT',
        'scope': 'Audit of maintainer-published same-box five-minute capacity table and coverage; no new performance runs.',
        'canonical_url': canonical['url'], 'canonical_commit': commit['sha'], 'canonical_git_blob': blob,
        'canonical_sha256': hashlib.sha256(text_bytes).hexdigest(), 'checks': checks,
        'official_conditions': {'target_cpus': 8, 'target_memory_gb_as_published': 16, 'postgres_version': 18,
                                'full_seed': True, 'load_generator_separate_machine': True,
                                'hold_measured_seconds': 300, 'p95_strictly_below_ms': 500,
                                'p99_strictly_below_ms': 1000, 'error_rate_strictly_below': 0.01},
        'coverage': {'scored_rows': len(scored), 'scored_submission_prs': len(scored_prs), 'scored_examples': 4,
                     'explicit_unscored_prs': len(unscored), 'submission_prs_in_inventory': len(heads),
                     'unlisted_prs': [r['pr'] for r in gaps], 'all_merged_submission_prs_scored': merged_prs <= scored_prs,
                     'all_submission_prs_have_published_result': set(heads) <= seen_prs},
        'scored_rows': scored, 'unscored_rows': unscored, 'unlisted_pull_requests': gaps,
        'published_ties_users_to_row_positions': {str(users): ranks for users, ranks in ties.items() if len(ranks) > 1},
        'our_result': {'pr': 32, 'published_rank': own['published_rank'], 'users': own['users'], 'rps': own['rps'],
                       'p95_ms': own['p95_ms'], 'p99_ms': own['p99_ms'], 'app_cpu_pct': own['app_cpu_pct_of_whole8cpu_box'],
                       'postgres_cpu_pct': own['postgres_cpu_pct_of_whole8cpu_box'],
                       'capacity_delta_vs_rust7_fraction': own['users'] / leader['users'] - 1,
                       'capacity_delta_vs_pr31_fraction': own['users'] / reference['users'] - 1,
                       'more_users_needed_to_match_rust7': leader['users'] - own['users'],
                       'users_for5pct_above_current_leader': leader['users'] * 1.05,
                       'more_users_needed_for5pct_above_current_leader': leader['users'] * 1.05 - own['users'],
                       'first_place_proven': False, 'at_least5pct_more_capacity_than_pr31': own['users'] >= reference['users'] * 1.05},
        'caveats': [
            'These are maintainer-reported official capacity results, not an independent replay or raw-trial audit.',
            'The leaderboard does not identify the exact measured commit, binary hash or runtime environment for every row; current PR heads must not be assumed measured.',
            'Raw probes, holds, per-endpoint data and second-by-second CPU are described as retained and available on request, but are not provided in this table.',
            'The SLO permits fewer than1% errors; exact error counts and zero-error status are not published.',
            'Latency and CPU columns are measured at different maximum user loads; they do not isolate implementation effects at matched load.',
            'Published notes about manual dependency pinning, prebuilt dependencies, worker-restart policy and draft state are retained verbatim; score and merge eligibility differ.',
            'Equal user counts are ties in measured capacity; the canonical row order is preserved without inventing a tie-break rule.',
            'No ARM Mac result is substituted into the official x86 leaderboard. Historical local invalid attempts remain in their original evidence record.',
        ],
        'raw_input_sha256': {str(p): digest(p) for p in inputs},
        'auditor_sha256': digest(Path(__file__)), 'new_capacity_benchmarks_executed': False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('/private/tmp/multicore-comparison-20261023'))
    a = p.parse_args()
    out = a.root / 'audit/comparison-check.json'
    result = compare(a.root / 'inventory', a.root / 'audit/canonical-leaderboard.json', a.root / 'audit/canonical-current-leaderboard.json')
    from check_export import check_export
    result['derived_export_audit'] = check_export(a.root, result)
    if result['derived_export_audit'] and result['derived_export_audit']['status'] != 'PASS':
        result['status'] = 'FAIL_PUBLISHED_TABLE_AUDIT'
    result['export_auditor_sha256'] = digest(Path(__file__).with_name('check_export.py'))
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'output': str(out), 'status': result['status'], 'checks': len(result['checks']),
                      'failed': [c for c in result['checks'] if not c['pass']], 'coverage': result['coverage'], 'our_result': result['our_result'],
                      'derived_export_status': result['derived_export_audit']['status'] if result['derived_export_audit'] else None,
                      'derived_export_failed': [c for c in (result['derived_export_audit'] or {}).get('checks', []) if not c['pass']]}))


if __name__ == '__main__':
    main()
