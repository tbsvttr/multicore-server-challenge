#!/usr/bin/env python3
"""Additional black-box JWT checks. Requires a running owned seeded server; writes no data."""
import argparse
import base64
import hashlib
import hmac
import json
import pathlib
import time
import urllib.error
import urllib.request

p = argparse.ArgumentParser()
p.add_argument('--base', required=True)
p.add_argument('--secret', required=True)
p.add_argument('--out', required=True)
a = p.parse_args()
results = []

def encode(b):
    return base64.urlsafe_b64encode(b).decode().rstrip('=')

def token(claims, header=None, secret=None):
    header = header or {'alg': 'HS256', 'typ': 'JWT'}
    b = '.'.join(encode(json.dumps(x, separators=(',', ':')).encode()) for x in [header, claims])
    return b + '.' + encode(hmac.digest((secret or a.secret).encode(), b.encode(), 'sha256'))

def request(name, path, tok, expect):
    headers = {} if tok is None else {'Authorization': 'Token ' + tok}
    req = urllib.request.Request(a.base.rstrip('/') + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            status, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read()
    record = {'name': name, 'path': path, 'expected': expect, 'status': status, 'pass': status == expect}
    if status == 401:
        try:
            obj = json.loads(body)
            record['error_shape'] = isinstance(obj['errors']['body'], list)
            record['pass'] &= record['error_shape']
        except (ValueError, KeyError, TypeError):
            record['error_shape'] = False
            record['pass'] = False
    results.append(record)

now = int(time.time())
valid_claims = {'sub': '1', 'iat': now, 'exp': now + 3600}
good = token(valid_claims)
request('valid required auth', '/api/user', good, 200)
request('valid optional auth', '/api/articles?limit=1', good, 200)
request('anonymous optional auth', '/api/articles?limit=1', None, 200)
request('missing required auth', '/api/user', None, 401)
request('alternate HS256 header key order', '/api/user', token(valid_claims, {'typ': 'JWT', 'alg': 'HS256'}), 200)
request('HS256 header without typ', '/api/user', token(valid_claims, {'alg': 'HS256'}), 200)

invalid = {
    'wrong key': token(valid_claims, secret=a.secret + '-wrong'),
    'missing signature': good.rsplit('.', 1)[0] + '.',
    'extra segment': good + '.x',
    'empty token': '',
    'bad base64': '!!!!.!!!!.!!!!',
    'expired': token({**valid_claims, 'exp': now - 10}),
    'missing exp': token({'sub': '1', 'iat': now}),
    'string exp': token({**valid_claims, 'exp': str(now + 3600)}),
    'future nbf': token({**valid_claims, 'nbf': now + 3600}),
    'numeric sub': token({**valid_claims, 'sub': 1}),
    'negative sub': token({**valid_claims, 'sub': '-1'}),
    'overflow sub': token({**valid_claims, 'sub': '9223372036854775808'}),
    'zero sub': token({**valid_claims, 'sub': '0'}),
    'wrong alg none': token(valid_claims, {'alg': 'none'}),
    'wrong alg RS256': token(valid_claims, {'alg': 'RS256'}),
}
for name, tok in invalid.items():
    for path in ['/api/user', '/api/articles?limit=1']:
        request(name, path, tok, 401)

# A previously accepted token must stop working when its exp passes.
soon = token({**valid_claims, 'exp': int(time.time()) + 2})
request('exp before deadline', '/api/user', soon, 200)
time.sleep(2.2)
request('same token after deadline', '/api/user', soon, 401)
request('valid token after invalid requests', '/api/user', good, 200)

out = {'scope': 'additional JWT black-box checks; original conformance suite remains authoritative',
       'base': a.base, 'checks': len(results), 'passed': sum(r['pass'] for r in results),
       'all_passed': all(r['pass'] for r in results), 'results': results}
pathlib.Path(a.out).write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({k: out[k] for k in ['checks', 'passed', 'all_passed']}))
raise SystemExit(0 if out['all_passed'] else 1)
