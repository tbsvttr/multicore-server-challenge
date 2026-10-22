#!/usr/bin/env python3
"""Paired ARTICLE_BATCH=0/1 correctness check against one disposable fixture DB.

Record with the feature off, restart the server with it on against the same DB,
then check. The check briefly holds an ACCESS EXCLUSIVE article-table lock to
force overlapping requests and witnesses execution of the shared article SQL.
"""
import argparse
import base64
import concurrent.futures
import contextlib
import hmac
import json
import os
import pathlib
import select
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('mode', choices=['record', 'check', 'cleanup'])
p.add_argument('--base', default=os.environ.get('BASE'))
p.add_argument('--secret', default=os.environ.get('JWT_SECRET'))
p.add_argument('--database-url', default=os.environ.get('DATABASE_URL'))
p.add_argument('--reference', required=True)
p.add_argument('--out')
p.add_argument('--concurrency', type=int, default=256)
p.add_argument('--requests', type=int, default=512)
a = p.parse_args()
if a.mode != 'cleanup' and (not a.base or not a.secret):
    p.error('BASE and JWT_SECRET or --base/--secret are required')
pg_env = os.environ.copy()
if a.database_url:
    u = urllib.parse.urlsplit(a.database_url)
    pg_env['PGDATABASE'] = urllib.parse.unquote(u.path.lstrip('/'))
    for k, v in [('PGHOST', u.hostname), ('PGPORT', str(u.port or 5432)),
                 ('PGUSER', urllib.parse.unquote(u.username or '')),
                 ('PGPASSWORD', urllib.parse.unquote(u.password or ''))]:
        if v and k not in pg_env:
            pg_env[k] = v
dbname = pg_env.get('PGDATABASE', '')
if not dbname or dbname in {'postgres', 'template0', 'template1', 'conduit_seed', 'conduit_dev'}:
    p.error('requires a disposable database clone, never a seed or system database')
psql = ['psql', '-X', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-d', dbname]

def q(s):
    return "'" + s.replace("'", "''") + "'"

def sql(s):
    r = subprocess.run(psql + ['-c', s], env=pg_env, text=True, capture_output=True, timeout=15)
    if r.returncode:
        raise RuntimeError('psql failed: ' + r.stderr.strip())
    return r.stdout.strip()

def enc(b):
    return base64.urlsafe_b64encode(b).decode().rstrip('=')

def token(uid):
    now = int(time.time())
    b = '.'.join(enc(json.dumps(x, separators=(',', ':')).encode()) for x in
                 [{'alg': 'HS256', 'typ': 'JWT'}, {'sub': str(uid), 'iat': now, 'exp': now + 600}])
    return b + '.' + enc(hmac.digest(a.secret.encode(), b.encode(), 'sha256'))

def api(case):
    headers = {} if case['viewer'] == 0 else {'Authorization': 'Token ' + token(case['viewer'])}
    req = urllib.request.Request(a.base.rstrip('/') + '/api/articles/' + urllib.parse.quote(case['slug'], safe=''), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            status, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read()
    obj = json.loads(body)
    # Error text is deliberately unspecified; retain only the required error shape.
    if status == 404:
        assert isinstance(obj['errors']['body'], list), obj
        obj = {'errors': {'body_is_list': True}}
    return {'status': status, 'body': obj}

def make_fixture():
    nonce = 'article_probe_' + uuid.uuid4().hex
    hashed = '$2a$10$ZSfEoPvlcsj2XfvsSeK25em4NZ9Jm7ntGqXuLgQfHEeZPYB8899wq'
    sql('BEGIN; INSERT INTO users(username,email,password_hash) VALUES ' + ','.join(
        '(' + ','.join([q(nonce + '_' + n), q(nonce + '_' + n + '@example.com'), q(hashed)]) + ')'
        for n in ['a', 'b', 'c']) + '; COMMIT;')
    users = json.loads(sql("SELECT json_object_agg(right(username,1),id) FROM users WHERE username IN (" +
                           ','.join(q(nonce + '_' + n) for n in ['a', 'b', 'c']) + ')'))
    slugs = [nonce + '-first', nonce + '-grün-🌱', nonce + '-third']
    body = 'Original body: Grüße 🌱 "quotes" \\ backslash\nnew line\tTabbed. ' * 24
    for i, slug in enumerate(slugs):
        author = users['b'] if i == 2 else users['a']
        sql('INSERT INTO articles(slug,author_id,title,description,body,created_at,updated_at) VALUES (' +
            ','.join([q(slug), str(author), q('Über 🌱 "batch" ' + str(i)), q('Description — 空'), q(body),
                      q('2026-10-22T00:00:00Z'), q('2026-10-22T00:00:00Z')]) + ')')
    articles = json.loads(sql('SELECT json_object_agg(slug,id) FROM articles WHERE slug IN (' + ','.join(map(q, slugs)) + ')'))
    tags = [nonce + '-é', nonce + '-空', nonce + '-a']
    sql('BEGIN; INSERT INTO tags(name) VALUES ' + ','.join('(' + q(t) + ')' for t in tags) + '; ' +
        'INSERT INTO article_tags(article_id,tag_id) SELECT a.id,t.id FROM articles a CROSS JOIN tags t WHERE a.id IN (' +
        ','.join(str(v) for v in articles.values()) + ') AND t.name IN (' + ','.join(map(q, tags)) + '); ' +
        f"INSERT INTO favorites(user_id,article_id) VALUES ({users['b']},{articles[slugs[0]]}),({users['a']},{articles[slugs[2]]}); " +
        f"INSERT INTO follows(follower_id,followee_id) VALUES ({users['b']},{users['a']}),({users['a']},{users['b']}); COMMIT;")
    return {'nonce': nonce, 'users': users, 'slugs': slugs, 'articles': articles, 'tags': tags, 'body': body}

def mutate(f, changed):
    aid = f['articles'][f['slugs'][0]]
    c, author = f['users']['c'], f['users']['a']
    if changed:
        body, stamp = 'COMMITTED UPDATE: 世界 🌱 \\ "fresh"\n', '2026-10-22T00:00:01Z'
        writes = (f'INSERT INTO favorites(user_id,article_id) VALUES ({c},{aid}) ON CONFLICT DO NOTHING; '
                  f'INSERT INTO follows(follower_id,followee_id) VALUES ({c},{author}) ON CONFLICT DO NOTHING; ')
    else:
        body, stamp = f['body'], '2026-10-22T00:00:00Z'
        writes = (f'DELETE FROM favorites WHERE user_id={c} AND article_id={aid}; '
                  f'DELETE FROM follows WHERE follower_id={c} AND followee_id={author}; ')
    sql('BEGIN; UPDATE articles SET body=' + q(body) + ',updated_at=' + q(stamp) + f' WHERE id={aid}; ' + writes + 'COMMIT;')

def cleanup(f):
    sql('BEGIN; DELETE FROM articles WHERE id IN (' + ','.join(str(v) for v in f['articles'].values()) + '); ' +
        'DELETE FROM users WHERE id IN (' + ','.join(str(v) for v in f['users'].values()) + '); ' +
        'DELETE FROM tags WHERE name IN (' + ','.join(map(q, f['tags'])) + '); COMMIT;')

def cases(f):
    out = []
    for slug in [f['nonce'] + '-missing-first', *f['slugs'], f['nonce'] + '-不存在-missing-last']:
        for viewer in [0, *f['users'].values()]:
            out.append({'slug': slug, 'viewer': viewer})
    return out

def marker(proc, want):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError('locking transaction exited: ' + proc.stderr.read())
        ready, _, _ = select.select([proc.stdout], [], [], 0.1)
        if ready and proc.stdout.readline().strip() == want:
            return
    raise TimeoutError('no transaction marker ' + want)

def concurrent_check(cases_, expected):
    proc = subprocess.Popen(psql, env=pg_env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1)
    witness, errors = None, []
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency)
    futures = []
    try:
        proc.stdin.write("BEGIN; LOCK TABLE articles IN ACCESS EXCLUSIVE MODE; SELECT 'LOCKED';\n")
        proc.stdin.flush()
        marker(proc, 'LOCKED')
        futures = [(i % len(cases_), executor.submit(api, cases_[i % len(cases_)])) for i in range(a.requests)]
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            waiting = sql("SELECT json_agg(json_build_object('pid',pid,'wait_event_type',wait_event_type,'query',query)) "
                          "FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() "
                          "AND wait_event_type='Lock' AND query LIKE '%slugs AS (SELECT DISTINCT slug FROM r)%'")
            if waiting and waiting != 'null':
                witness = json.loads(waiting)
                break
            time.sleep(0.04)
    finally:
        with contextlib.suppress(Exception):
            proc.stdin.write('ROLLBACK;\n')
            proc.stdin.flush()
            proc.stdin.close()
            proc.wait(timeout=3)
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=3)
    try:
        for idx, future in futures:
            try:
                actual = future.result(timeout=30)
                if actual != expected[idx]:
                    errors.append({'case': cases_[idx], 'actual': actual, 'expected': expected[idx]})
            except Exception as e:
                errors.append({'case': cases_[idx], 'error': type(e).__name__ + ': ' + str(e)})
    finally:
        executor.shutdown(wait=True)
    return {'requests': len(futures), 'shared_SQL_witness': witness, 'differences': errors,
            'pass': bool(witness) and not errors, 'lock_stderr': proc.stderr.read()}

reference = pathlib.Path(a.reference)
if a.mode == 'record':
    f = make_fixture()
    reference.write_text(json.dumps({'database': dbname, 'fixture': f}, indent=2) + '\n')
    cs = cases(f)
    before = [api(c) for c in cs]
    mutate(f, True)
    try:
        after = [api(c) for c in cs]
    finally:
        mutate(f, False)
    out = {'database': dbname, 'fixture': f, 'cases': cs, 'before': before, 'after': after,
           'scope': 'sequential ARTICLE_BATCH=0 reference; fixture retained for paired check'}
    reference.write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'recorded_cases': len(cs), 'database': dbname, 'reference': str(reference)}))
elif a.mode == 'cleanup':
    r = json.loads(reference.read_text())
    assert r['database'] == dbname
    cleanup(r['fixture'])
    print('fixture cleaned')
else:
    if not a.out:
        p.error('--out is required in check mode')
    r = json.loads(reference.read_text())
    assert r['database'] == dbname
    out = {'scope': 'paired live article batching correctness comparison', 'database': dbname,
           'reference': str(reference), 'pass': False}
    try:
        out['before'] = concurrent_check(r['cases'], r['before'])
        mutate(r['fixture'], True)
        out['after_committed_update'] = concurrent_check(r['cases'], r['after'])
        out['pass'] = out['before']['pass'] and out['after_committed_update']['pass']
    except Exception as e:
        out['error'] = type(e).__name__ + ': ' + str(e)
    finally:
        try:
            mutate(r['fixture'], False)
            out['fixture_restored'] = True
        except Exception as e:
            out['fixture_restored'] = False
            out['restore_error'] = type(e).__name__ + ': ' + str(e)
            out['pass'] = False
        pathlib.Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'pass': out['pass'], 'error': out.get('error'),
                      'requests': sum(out.get(k, {}).get('requests', 0) for k in ['before', 'after_committed_update']),
                      'differences': sum(len(out.get(k, {}).get('differences', [])) for k in ['before', 'after_committed_update'])}))
    raise SystemExit(0 if out['pass'] else 1)
