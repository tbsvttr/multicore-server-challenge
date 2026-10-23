"""Compare the derived one-row export against the independently parsed table."""
import hashlib
import json
import math
import re


def check_export(root, published):
    source = root / 'official-comparison.json'
    if not source.exists():
        return None
    obj = json.loads(source.read_text())
    canonical = {r['id']: r for r in published['scored_rows']}
    rows, history = obj['rows'], obj['historical_closed_records']
    checks = []

    def check(name, passed, detail=None):
        checks.append({'check': name, 'pass': bool(passed), **({'detail': detail} if detail is not None else {})})

    check('31_unique_current_rows', len(rows) == len({r['id'] for r in rows}) == 31)
    check('29_scored_plus_active_unscored5_and17',
          [r['id'] for r in rows[:29]] == list(canonical)
          and {r['pr'] for r in rows[29:]} == {5, 17}
          and all(r['official_score'] is None for r in rows[29:]))
    check('historical14_18_21_retained_once_outside_current_table',
          {r['pr'] for r in history} == {14, 18, 21} and len(history) == 3
          and not {14, 18, 21} & {r['pr'] for r in rows})
    for row in rows:
        name, score = row['id'], row['official_score']
        check(name + ':no_new_local_run_or_measured_source_claim', row['local_run_this_refresh'] == 'NOT_RUN'
              and row['measured_source_revision_known'] is False)
        if score is None:
            check(name + ':unscored_gaps_are_null', all(row[k] is None for k in
                  ['gap_users_vs_ours', 'gap_percent_vs_ours', 'gap_users_vs_leader', 'gap_percent_vs_leader']))
            continue
        raw = canonical[name]
        fields = {'rank': 'published_rank', 'users': 'users', 'requests_per_second': 'rps',
                  'p95_ms': 'p95_ms', 'p99_ms': 'p99_ms', 'front': 'front', 'note': 'maintainer_note'}
        check(name + ':all_published_values_and_note_preserved', row['name'] == raw['submission']
              and all(score[k] == raw[v] for k, v in fields.items()))
        percentages = [int(n) for n in re.findall(r'(\d+)%', score['cpu_app_postgres'])]
        expected = [raw['app_cpu_pct_of_whole8cpu_box'], raw['postgres_cpu_pct_of_whole8cpu_box']]
        if raw['front'] == 'nginx':
            expected.append(raw['nginx_cpu_pct_of_whole8cpu_box'])
        check(name + ':whole_box_cpu_values_preserved', percentages == expected)
        for reference, users in [('ours', 65000), ('leader', 100000)]:
            check(name + ':signed_gap_vs_' + reference,
                  row['gap_users_vs_' + reference] == raw['users'] - users
                  and math.isclose(row['gap_percent_vs_' + reference], 100 * (raw['users'] / users - 1), abs_tol=1e-11))
    failed18 = next(r for r in history if r['pr'] == 18)
    raw18 = next(r for r in published['unscored_rows'] if r['pr'] == 18)
    raw5 = next(r for r in published['unscored_rows'] if r['pr'] == 5)
    check('official_failure_reasons_retained_for5_and18',
          failed18['official_unscored_reason'] == raw18['maintainer_note']
          and next(r for r in rows if r['pr'] == 5)['official_unscored_reason'] == raw5['maintainer_note'])
    check('same_pinned_official_snapshot', obj['upstream_commit'] == published['canonical_commit']
          and obj['leaderboard_blob_sha1'] == published['canonical_git_blob']
          and obj['leaderboard_sha256'] == published['canonical_sha256'])
    md = root / 'official-comparison.md'
    md_checks = []
    if md.exists():
        text = md.read_text()
        table = [[x.strip() for x in line.strip().strip('|').split('|')]
                 for line in text.splitlines() if line.startswith('| ')]
        header = table[0]
        body = [r for r in table[1:] if r[0] == '—' or r[0].isdigit()]
        check('markdown31_rows', len(body) == 31)
        fields = {label: header.index(label) for label in
                  ['Official rank', 'Implementation', 'Users', 'Req/s', 'p95 / p99 ms', 'Front', 'CPU app / PG', 'Caveat']}
        for saved, row in zip(rows, body):
            score = saved['official_score']
            expected_name = ('#' + str(saved['pr']) + ' ' if saved['pr'] else '') + saved['name']
            check(saved['id'] + ':markdown_name_and_link', '[' + expected_name + '](' in row[fields['Implementation']])
            if score:
                check(saved['id'] + ':markdown_published_values',
                      row[fields['Official rank']] == str(score['rank'])
                      and row[fields['Users']] == format(score['users'], ',')
                      and row[fields['Req/s']] == format(int(score['requests_per_second']), ',')
                      and row[fields['p95 / p99 ms']] == f"{score['p95_ms']:g} / {score['p99_ms']:g}"
                      and row[fields['Front']] == score['front']
                      and row[fields['CPU app / PG']] == score['cpu_app_postgres']
                      and row[fields['Caveat']] == (score['note'] or '—'))
            else:
                check(saved['id'] + ':markdown_unscored_not_zero', row[fields['Users']] == '—'
                      and row[fields['Official rank']] == '—')
        check('different_load_latency_and_source_version_limits_disclosed',
              'not matched-load' in text and 'do not prove the exact revision' in text)
    return {'status': 'PASS' if all(c['pass'] for c in checks) else 'FAIL', 'checks': checks,
            'input_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [source, md] if p.exists()},
            'scope': 'All canonical values, CPU/latency/note fields, signed JSON gaps,31current rows and3historical records; no benchmark replay.'}
