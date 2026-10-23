#!/usr/bin/env python3
"""Read-only audit of a predeclared one-arm80k profile and saved PG samples."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys
import time

OLD_AUDIT = Path('/private/tmp/multicore-research-20261022/audit')
sys.path.insert(0, str(OLD_AUDIT))
import analyze_multi as native_audit
from analyze_paired import GiB, check, inspect_budget, jsonl, read, setting_map, sha


def family(query):
    if query.startswith('SELECT x.id,'):
        return 'comments_read'
    if query.startswith('WITH r AS MATERIALIZED') and 'q(viewer, slug, ord)' in query:
        return 'batched_article_or_comments_read'
    batch = query.startswith('SELECT q.*, r.ord FROM unnest(')
    shared = query.startswith('WITH r AS MATERIALIZED')
    if 'a.author_id IN (SELECT fo.followee_id' in query or ('FROM follows fo CROSS JOIN LATERAL' in query and 'LIMIT 1000' in query):
        return 'feed_read'
    if query.startswith('SELECT a.slug,') and 'currval' in query:
        return 'created_article_readback'
    if query.startswith('SELECT a.slug,'):
        return 'single_article_read'
    if query.startswith('SELECT convert_to(array_to_json(array_agg') or query.startswith('SELECT array_to_json(array_agg'):
        return 'tags_read'
    if query.startswith('SELECT u.username,'):
        return 'profile_read'
    if query.startswith('SELECT id, username, email'):
        return 'user_or_login_read'
    if 'WITH c AS (INSERT INTO comments' in query:
        return 'create_comment'
    if 'INSERT INTO favorites' in query:
        return 'favorite'
    if 'DELETE FROM favorites' in query:
        return 'unfavorite'
    if 'DELETE FROM follows' in query:
        return 'unfollow'
    if 'INSERT INTO follows' in query:
        return 'follow'
    if query.startswith('INSERT INTO article_tags'):
        return 'create_article_tags'
    if query.startswith('INSERT INTO articles'):
        return 'create_article'
    if query.startswith('WITH t AS (SELECT id, author_id FROM articles'):
        return 'update_or_delete_article'
    if query.startswith('WITH c AS (SELECT') or batch or shared:
        suffix = '_shared' if shared else '_batched' if batch else ''
        if 'FROM article_tags at WHERE at.tag_id' in query:
            return 'list_tag' + suffix
        if 'author_id = (SELECT u.id' in query or 'author_id = (SELECT au.id' in query:
            return 'list_author' + suffix
        if 'FROM favorites f WHERE f.user_id = (SELECT fu.id' in query:
            return 'list_favorited' + suffix
        return 'list_all' + suffix
    return 'unclassified'


def sample_profile(path, meta):
    rows = jsonl(path)
    start, end = meta['window_start_ms'] * 1000000, meta['window_end_ms'] * 1000000
    selected = [(i + 1, row) for i, row in enumerate(rows) if start <= row['wall_ns'] <= end]
    states, waits, active_waits, families = collections.Counter(), collections.Counter(), collections.Counter(), {}
    query_stats = {}
    for line, row in selected:
        for backend in row.get('sample', {}).get('backends', []):
            state = backend['state']
            wait = (backend.get('wait_type') or 'none') + '/' + (backend.get('wait_event') or 'none')
            states[state] += 1; waits[state + ':' + wait] += 1
            if state != 'active':
                continue
            active_waits[wait] += 1
            query = backend.get('query', '')
            label, digest = family(query), hashlib.sha256(query.encode()).hexdigest()
            entry = families.setdefault(label, {'active_backend_observations': 0, 'active_no_wait_observations': 0,
                                                'waits': collections.Counter(), 'raw_line_refs': [], 'query_sha256': set()})
            entry['active_backend_observations'] += 1
            entry['active_no_wait_observations'] += backend.get('wait_type') is None
            entry['waits'][wait] += 1; entry['raw_line_refs'].append(line); entry['query_sha256'].add(digest)
            q = query_stats.setdefault(digest, {'family': label, 'captured_query': query,
                'captured_utf8_bytes': len(query.encode()), 'possibly_truncated_at1023bytes': len(query.encode()) >= 1023,
                'active_backend_observations': 0, 'active_no_wait_observations': 0,
                'first_raw_line': line, 'first_seen_wall_ns': row['wall_ns'], 'representative_pid': backend['pid']})
            q['active_backend_observations'] += 1; q['active_no_wait_observations'] += backend.get('wait_type') is None
            q['last_raw_line'] = line; q['last_seen_wall_ns'] = row['wall_ns']
    active, no_wait = states['active'], active_waits['none/none']
    for entry in families.values():
        entry.update(share_of_active_backend_observations=entry['active_backend_observations'] / active if active else None,
                     share_of_active_no_wait_observations=entry['active_no_wait_observations'] / no_wait if no_wait else None)
        entry['raw_line_refs'] = sorted(set(entry['raw_line_refs']))
        entry['query_sha256'] = sorted(entry['query_sha256'])
    offsets = [(r['wall_ns'] - r['monotonic_ns']) / 1e9 for r in rows]
    gaps = [(b['wall_ns'] - a['wall_ns']) / 1e9 for a, b in zip(rows, rows[1:])]
    counters = [(line, r) for line, r in selected if r.get('exit_code') == 0 and r.get('sample', {}).get('database')]
    database = None
    if len(counters) >= 2:
        first_line, first = counters[0]; last_line, last = counters[-1]
        elapsed = (last['monotonic_ns'] - first['monotonic_ns']) / 1e9
        before, after = first['sample']['database'], last['sample']['database']
        deltas = {k: after[k] - value for k, value in before.items() if isinstance(value, (int, float)) and isinstance(after.get(k), (int, float))}
        database = {'first_raw_line': first_line, 'last_raw_line': last_line, 'counter_interval_s': elapsed,
                    'first_wall_ns': first['wall_ns'], 'last_wall_ns': last['wall_ns'], 'deltas': deltas,
                    'all_counters_nondecreasing': all(x >= 0 for x in deltas.values()),
                    'buffer_hit_fraction_over_observed_counter_interval': deltas['blks_hit'] / (deltas['blks_hit'] + deltas['blks_read']),
                    'scope': 'Delayed cumulative statistics for the owned benchmark database over this sampled inner interval; not exact per-query accounting. The collector connects to postgres, so its own transactions are outside these target-database counters.'}
    return {'path': str(path), 'sha256': sha(path), 'total_samples': len(rows), 'measurement_samples': len(selected),
            'measurement_window_ms': [meta['window_start_ms'], meta['window_end_ms']],
            'raw_lines_in_measurement': [line for line, row in selected],
            'full_measurement_bracketed': bool(rows) and rows[0]['wall_ns'] <= start and rows[-1]['wall_ns'] >= end,
            'max_wall_gap_s': max(gaps, default=None), 'wall_monotonic_offset_range_s': max(offsets) - min(offsets) if offsets else None,
            'collector_errors': sum(r.get('exit_code') != 0 or 'sample' not in r for r in rows),
            'backend_counts_per_measurement_sample': dict(collections.Counter(len(r.get('sample', {}).get('backends', [])) for _, r in selected)),
            'state_backend_observations': dict(states), 'state_wait_backend_observations': dict(waits),
            'active_wait_backend_observations': dict(active_waits),
            'active_query_families': dict(sorted(families.items(), key=lambda x: -x[1]['active_backend_observations'])),
            'active_captured_queries': dict(sorted(query_stats.items(), key=lambda x: -x[1]['active_backend_observations'])),
            'database_statistics': database,
            'interpretation': 'Counts are point-sampled backend occupancy, not request mix, query CPU time, completed-query latency, or causal contribution. No-wait active backends may be running or runnable. Idle query_ms is last-query age, never charged as execution time.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--pg-samples', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    plan, events = read(args.run / 'plan.json'), jsonl(args.run / 'events.jsonl')
    checks, initial, frozen = [], read(args.run / 'target-initial.json'), {}
    check(checks, 'frozen_one_arm80k_diagnostic', plan.get('diagnostic_only') is True and plan['protocol']['order'] == [[1]]
          and plan['protocol']['pairs'] == 1 and plan['protocol']['users'] == 80000)
    check(checks, 'plan_hash_fixed', sha(args.run / 'plan.json') == (args.run / 'plan.sha256').read_text().strip())
    check(checks, 'one_planned_attempt_without_replacement', [e['id'] for e in events if e['event'] == 'attempt_start'] == ['01-p1-goose']
          and [e['id'] for e in events if e['event'] == 'attempt_complete'] == ['01-p1-goose'])
    check(checks, 'controller_finished_cleanly', any(e['event'] == 'controller_finished' for e in events)
          and all(e.get('error') is None for e in events if e['event'] == 'controller_finished'))
    for kind, cpus, memory in [('target', 8, 16 * GiB), ('load', 4, 4 * GiB)]:
        a, b = read(args.run / (kind + '-inspect.json')), read(args.run / (kind + '-final-inspect.json'))
        check(checks, kind + ':budget_and_identity_fixed', inspect_budget(a, cpus, memory) and inspect_budget(b, cpus, memory) and a['Id'] == b['Id'])
    target, load = read(args.run / 'target-inspect.json'), read(args.run / 'load-inspect.json')
    check(checks, 'separate_client_cgroup_shared_network', target['Id'] != load['Id'] and load['HostConfig']['NetworkMode'] == 'container:' + target['Id'])
    pg = setting_map(initial)
    check(checks, 'durable_postgres18_fixed', pg['server_version_num'][0].startswith('18') and pg['max_connections'][0] == '100'
          and all(pg[k][0] == 'on' for k in ['fsync', 'synchronous_commit', 'full_page_writes']))
    for case in plan['configuration']['cases']:
        path = args.run / 'frozen' / case['name']; meta = read(path / 'metadata.json'); frozen[case['name']] = meta
        actual = {str(p.relative_to(path / 'source')): sha(p) for p in (path / 'source').rglob('*') if p.is_file()}
        check(checks, case['name'] + ':binary_and_source_frozen', meta['case'] == case and sha(path / 'app') == meta['binary_sha256'] == case['expected_binary_sha256']
              and actual == meta['source_sha256'] and hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest() == meta['source_manifest_sha256'])
    tools = read(args.run / 'frozen-tool-sha256.json')
    check(checks, 'executed_tools_frozen', all(sha(args.run / 'tools' / name) == value for name, value in tools.items()))
    originals = read(args.run / 'tool-source-sha256.json')
    check(checks, 'native_generator_binary_pinned', originals.get('tools/loadgen') == '886eaa564c6cdab1a791534d6931d1b8eb9b5c21d1e1ebaaa2824616c4562cdb')
    check(checks, 'full_seed_template_fingerprint_proof', 'OK: conduit_seed matches the reference seed' in Path('/private/tmp/multicore-research-20261022/seed-full.log').read_text()
          and initial['official_source_sha256']['seed/make-seed.sh'] + '  /work/seed/make-seed.sh' in Path('/private/tmp/multicore-research-20261022/setup/upstream-sha256.txt').read_text())
    attempt = native_audit.assess_attempt(args.run / '01-p1-goose', plan, initial, frozen, all(c['pass'] for c in checks))
    meta = read(args.run / '01-p1-goose/box0.json')['meta']
    profile = sample_profile(args.pg_samples, meta)
    output = {'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'run': str(args.run),
              'scope': plan['scope'], 'status': 'PASS_ONE_ARM_LOCAL_EVIDENCE' if attempt['eligible'] and all(c['pass'] for c in checks) else 'INVALID_EVIDENCE',
              'checks': checks, 'attempt': attempt, 'pg_profile': profile,
              'source_head': initial['repo_head']['stdout'], 'stock_binary_sha256': frozen['goose']['binary_sha256'],
              'pg_sampler_source_sha256': sha(args.out.parent.parent / 'pg-sample.py'),
              'pg_sampler_scope': 'Inspected SELECT-only collector, connected to postgres as postgres; pg_stat_activity/pg_stat_database filtered to the owned benchmark database. Its CPU remains inside the target cgroup.',
              'track_io_timing': pg['track_io_timing'][0],
              'conclusions': [
                  'The observed workload at80k is a valid fixed-load diagnostic only; no sustainable capacity, paired gain or rank is proved.',
                  'Feed reads have the largest sampled no-wait active backend presence. Article/comments/list work also appears frequently, making those specific SQL paths reasonable optimization experiments.',
                  'WAL sync/write waits are observed, supporting a group-commit experiment; the profile does not establish its causal benefit or expected speedup.',
                  'No row-lock-type wait was observed in these samples. Brief waits can be missed; absence of samples is not proof of absence.',
                  'Most backend observations are idle. That does not imply PostgreSQL has unused CPU capacity or identify a server capacity ceiling.',
              ],
              'limitations': [
                  'The read-only PostgreSQL sampler itself consumes resources and is included in target CPU; this is not an uninstrumented capacity run.',
                  'Query text can be truncated by PostgreSQL activity tracking; classification uses recognizable captured prefixes and preserves each captured query/hash/raw-line reference.',
                  'pg_stat_activity occupancy is sampled, not accumulated CPU or statement latency. query_ms on idle records is not execution time.',
                  'Per-process PostgreSQL CPU is withheld when collector/background PID populations change; cgroup total CPU remains authoritative.',
                  'Database counter deltas can lag the actual workload. The sampler connects to postgres, so its own transactions are outside these target-database counters, although collector CPU remains inside the target cgroup. Zero blk_read_time with track_io_timing off does not prove zero I/O.',
                  'Original full-seed script verifies all7 tables; per-attempt clone independently counted users/articles only.',
              ], 'capacity_or_rank_proven': False,
              'code_sha256': {'profile_one_arm.py': sha(Path(__file__)), 'analyze_multi.py': sha(OLD_AUDIT / 'analyze_multi.py'),
                              'analyze_paired.py': sha(OLD_AUDIT / 'analyze_paired.py')},
              'raw_sha256': {str(p): sha(p) for p in args.run.rglob('*') if p.is_file()}}
    args.out.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    m = attempt.get('metrics', {})
    lines = ['# Stock80k profile audit', '', output['status'], '',
             f"Native req/s {m.get('rps')}; p95/p99 {m.get('p95_ms')}/{m.get('p99_ms')}ms; measured errors {m.get('errors')}; recorded timeline errors {attempt.get('observed_timeline_errors')}.",
             f"Target combined CPU {m.get('total_cpu_pct_of_8'):.3f}% of8CPU; client {attempt['load_monitor']['cgroup_quota_utilization_pct']:.3f}% of4CPU.",
             f"PG samples in native window: {profile['measurement_samples']}; backend observations: {profile['state_backend_observations']}.", '',
             '| Query family | Active observations | No-wait active observations | Share of no-wait active |', '|---|---:|---:|---:|']
    for name, entry in profile['active_query_families'].items():
        lines.append(f"| {name} | {entry['active_backend_observations']} | {entry['active_no_wait_observations']} | {entry['share_of_active_no_wait_observations']:.1%} |")
    lines.extend(['', 'Active waits: ' + json.dumps(profile['active_wait_backend_observations']), '', profile['interpretation'], ''])
    lines.extend(output['conclusions'] + [''] + output['limitations'])
    args.out.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'output': str(args.out), 'status': output['status'], 'failed': [c for c in checks if not c['pass']],
                      'attempt_classification': attempt['classification'], 'metrics': m, 'profile_observations': profile['state_backend_observations']}))


if __name__ == '__main__':
    main()
