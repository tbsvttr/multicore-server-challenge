#!/usr/bin/env python3
"""Prepare a disclosed, correctness-corrected portable PR31 comparator. No build."""
from pathlib import Path
import difflib, hashlib, json, shutil

here=Path(__file__).resolve().parent
original=Path('/private/tmp/multicore-research-20261022/pr31-source/submissions/goose-epoll-xeonfx')
ours=Path('/private/tmp/multicore-challenge-20261022/submissions/goose-native-tbsvttr')
license_path=Path('/private/tmp/multicore-challenge-20261022/LICENSE')
source=here/'source'
original_copy=here/'original-source'
assert not source.exists() and not original_copy.exists(), 'Reference already prepared; do not overwrite evidence.'
original_files=sorted(p.name for p in original.iterdir() if p.is_file())
assert len(original_files)==17, original_files
shutil.copytree(original,original_copy)
shutil.copytree(original,source)
shutil.copyfile(license_path,here/'LICENSE')
shutil.copyfile(license_path,source/'LICENSE')

# Only the syscall ABI and reliable pipe primitive cross into C. All JWT,
# SHA/HMAC, body parsing and JSON remain the credited original Goose code.
bridge=(ours/'native_sys.c').read_text()
bridge=bridge.replace('/* Portable syscall boundary for the inherited Goose epoll scheduler.\n   Our twelve-dollar-server-challenge PR #143 transport also crosses into C\n   before socket/epoll calls. Here the existing async Goose scheduler stays in\n   charge; C only translates the native ABI, including ARM\'s epoll padding. */',
'''/* Portable syscall/pipe boundary reused from tbsvttr's multicore Goose
   implementation (PR #32). This comparator otherwise retains XeonFX's PR #31
   scheduler and pure Goose JSON/HMAC. C translates the native syscall ABI,
   ARM epoll padding, and reliable delivery of completed bcrypt replies. */''')
assert '#include "json_fast.h"' in bridge
(source/'native_sys.c').write_text(bridge.replace('#include "json_fast.h"','#include "native_sys.h"'))
(source/'native_sys.h').write_text('''#ifndef PR31_REFERENCE_NATIVE_SYS_H
#define PR31_REFERENCE_NATIVE_SYS_H

#include <stdint.h>

/* Borrowed Goose slice ABI only. No native JSON or crypto operations. */
#pragma pack(push, 1)
typedef struct { const uint8_t *data; int64_t len; } bytes;
typedef struct { uint8_t *data; int64_t len; } mutable_bytes;
#pragma pack(pop)

#endif
''')
p=source/'sys.goose';s=p.read_text()
s=s.replace('// The Linux calls the server makes, bound straight to glibc. A Goose slice crosses as { data, len } by value, which\n// x86-64 passes in two registers, so `send(fd, buf, flags)` here is C\'s `send(fd, buf.data, buf.len, flags)`.\n// Nothing variadic is called (no fcntl or ioctl): sockets are made non-blocking by SOCK_NONBLOCK instead.',
'''// Portable reference adaptation: C explicitly translates slice arguments and
// native epoll layout. The original Goose scheduler and all JSON/crypto remain.
// x86 epoll stays zero-copy; ARM's native 16-byte event layout is translated.''')
for n in ('read','write','recv','send','getrandom','epoll_ctl','epoll_wait'):
    old=f'extern "{n}" fn sys_{n}'
    assert old in s,n
    s=s.replace(old,f'extern "native_sys_{n}" fn sys_{n}')
needle='extern "native_sys_write" fn sys_write(fd: i32, buf: const u8[:]) -> i64;'
assert needle in s
s=s.replace(needle,needle+'\nextern fn native_write_atomic_reply(fd: i32, buf: const u8[:]) -> i64;')
p.write_text(s)
p=source/'bcrypt.goose';s=p.read_text();needle='    sys_write(job.reply_fd, bytes);';assert s.count(needle)==1
s=s.replace(needle,'''    // Same correctness fix as the candidate: retain completed replies through backpressure.
    if native_write_atomic_reply(job.reply_fd, bytes) != REPLY_SIZE { abort("bcrypt reply delivery failed"); }''');p.write_text(s)
p=source/'main.goose';s=p.read_text();needle='    readers = env_int("PG_READERS", 3);';assert s.count(needle)==1
s=s.replace(needle,needle+'''
    // Same configuration guard as the candidate; default workers/readers are unchanged.
    if readers > 94 { abort("PG_READERS leaves no room within the 95-connection limit"); }
    if workers > 95 / (readers + 1) { abort("WORKERS * (PG_READERS + 1) must be at most 95"); }''');p.write_text(s)
p=source/'routes.goose';s=p.read_text();needle='    bind_end(msg, b);\n    submit(slot, msg, auth);\n}\n\nfn create_article';assert s.count(needle)==1
s=s.replace(needle,'''    bind_end(msg, b);
    if kind == K_FAVORITE || kind == K_UNFAVORITE { set_ctx(slot, pval); }
    submit(slot, msg, auth);
}

// Same correctness fix as the candidate: read the committed favorite count.
// Save only the following read for retries; a committed mutation is never replayed.
fn favorite_committed(slot: i64, rows: const u8[:]) {
    if first_row(rows).len == 0 { fail(slot, 404, "article not found"); return; }
    let viewer = conns[slot].viewer;
    begin(slot, K_ARTICLE, viewer);
    var msg: u8[>..] = [];
    let b = stmt(slot, msg, ST_ARTICLE, 2);
    param_int(msg, viewer);
    param_text(msg, ctx(slot));
    bind_end(msg, b);
    submit(slot, msg, false);
}

fn create_article''')
needle='    match c.kind {\n        K_REGISTER, K_CURRENT, K_UPDATE_USER => {';assert s.count(needle)==1
s=s.replace(needle,'    match c.kind {\n        K_FAVORITE, K_UNFAVORITE => { favorite_committed(slot, rows); return; },\n        K_REGISTER, K_CURRENT, K_UPDATE_USER => {')
needle='        K_ARTICLE, K_FAVORITE, K_UNFAVORITE, K_CREATE, K_UPDATE_ARTICLE => {';assert s.count(needle)==1
s=s.replace(needle,'        K_ARTICLE, K_CREATE, K_UPDATE_ARTICLE => {');p.write_text(s)
p=source/'sql.goose';s=p.read_text();start=s.index('        // The toggles write and read in one statement,')
end=s.index('        // No row: unknown article.',start)
s=s[:start]+'''        // Same correctness fix as the candidate: mutate first, then read after commit.
        ST_FAVORITE => out.append("WITH t AS (SELECT id FROM articles WHERE slug = $2), w AS (INSERT INTO favorites (user_id, article_id) SELECT $1, id FROM t ON CONFLICT DO NOTHING) SELECT id FROM t"),
        ST_UNFAVORITE => out.append("WITH t AS (SELECT id FROM articles WHERE slug = $2), w AS (DELETE FROM favorites WHERE user_id = $1 AND article_id = (SELECT id FROM t)) SELECT id FROM t"),
'''+s[end:];p.write_text(s)

# Match candidate compiler generation/optimization, but link only the syscall
# bridge: the comparison cannot accidentally acquire native JSON or HMAC.
s=(ours/'build.sh').read_text()
s=s.replace('# Build the pinned Goose compiler from source, then generated Goose and our\n# native byte/crypto primitives together. No prebuilt application is downloaded.',
'''# Portable PR31 reference: same pinned compiler and optimization as candidate.
# Only native syscall/pipe ABI code is linked. JSON and HMAC remain Goose.''')
needle='.build/main.c json_fast.c native_crypto.c native_sys.c';assert needle in s
s=s.replace(needle,'.build/main.c native_sys.c').replace('    -lcrypto -lm -pthread -o bin/conduit','    -lm -pthread -o bin/conduit')
(source/'build.sh').write_text(s)
s=(ours/'install.sh').read_text().replace(' libssl-dev','')
(source/'install.sh').write_text(s)
p=source/'.gitignore';p.write_text(p.read_text()+'.build/\n.deps/\n')
for n in ('build.sh','install.sh','start.sh'):
    (source/n).chmod(0o755)

(source/'README.md').write_text("> **Local portable, correctness-corrected PR #31 reference.** This is a disclosed derivative of XeonFX's pinned source, prepared for a same-host comparison. It adds a C syscall/epoll ABI bridge, reliable bcrypt reply delivery, a PostgreSQL connection guard, and committed favorite responses. JSON and HMAC remain the original Goose implementation. The upstream GCP figures below are historical PR #31 claims, not measurements of this derivative and not an official score. See [the reference manifest](../manifest.json) and [comparison notes](../README.md).\n\n"+(source/'README.md').read_text())
protected=('crypto.goose','jwt.goose','http.goose','server.goose','pg.goose','buf.goose','bcrypt_tables.goose','start.sh')
for n in protected:
    assert (source/n).read_bytes()==(original/n).read_bytes(),n
assert not (source/'json_fast.c').exists()
assert not (source/'native_crypto.c').exists()
assert not any('ARTICLE_BATCH' in p.read_text() or 'ST_BATCH_ARTICLE' in p.read_text() for p in source.glob('*.goose'))
assert 'jwt_key = hmac_key(secret);' in (source/'main.goose').read_text()
assert 'var jwt_key = hmac_key("");' in (source/'server.goose').read_text()
assert 'json::format_string(out, token);' in (source/'routes.goose').read_text()
assert 'native_hmac_sha256' not in ''.join(p.read_text() for p in source.glob('*') if p.is_file())

all_names=sorted(set(original_files)|{p.name for p in source.iterdir() if p.is_file()})
reasons={
'.gitignore':['Ignore generated C, compiler archive, and build output.'],
'README.md':['Prominently disclose portability/correctness modifications and distinguish historical upstream GCP claims from this unmeasured reference.'],
'LICENSE':['Preserve upstream MIT terms inside the independently copied source folder.'],
'native_sys.c':['Translate Goose slice arguments and ARM epoll layout explicitly; keep x86 epoll zero-copy.','Apply the same reliable atomic bcrypt pipe-delivery correctness fix as the candidate.'],
'native_sys.h':['Define only borrowed slice ABI layouts; contains no JSON/HMAC primitive.'],
'sys.goose':['Rename slice/epoll externs to the portable native ABI bridge.','Expose reliable atomic bcrypt reply delivery.'],
'bcrypt.goose':['Retain completed replies through EINTR/full-pipe backpressure; fail explicitly on permanent delivery error.'],
'main.goose':['Reject invalid PostgreSQL connection configurations above 95; preserve original pure-Goose HMAC key and default process counts.'],
'routes.goose':['Read favorite/unfavorite responses after writer commit; saved read retries cannot replay committed mutations.','Preserve original Goose JSON formatting and JWT signatures.'],
'sql.goose':['Favorite mutations return existence; subsequent ST_ARTICLE reads the committed article/count.'],
'build.sh':['Pin the full same Goose commit and source archive SHA256 as the candidate.','Use identical -O2 standalone generation and GCC -O3/-march=native/LTO2 optimization.','Link only native_sys.c and system math/thread libraries; no native JSON/OpenSSL HMAC.'],
'install.sh':['Install Ubuntu24 C/C++/CMake/curl/CA tools needed by the pinned archive bootstrap; no OpenSSL application dependency.']}
rows=[];patch=[]
for n in all_names:
    a=(original/n).read_bytes() if (original/n).exists() else None
    b=(source/n).read_bytes() if (source/n).exists() else None
    status='added' if a is None else 'unchanged' if a==b else 'modified'
    row={'path':n,'status':status,'original_sha256':hashlib.sha256(a).hexdigest() if a is not None else None,'reference_sha256':hashlib.sha256(b).hexdigest() if b is not None else None}
    if status!='unchanged':
        row['reason']=reasons[n]
        patch.extend(difflib.unified_diff(a.decode().splitlines(True) if a is not None else [],b.decode().splitlines(True) if b is not None else [],fromfile='a/'+n if a is not None else '/dev/null',tofile='b/'+n if b is not None else '/dev/null'))
    rows.append(row)
record={'label':'PR31 portable, correctness-corrected local reference','upstream_repo':'XeonFX/multicore-server-challenge','upstream_pr':'https://github.com/arjaythedev/multicore-server-challenge/pull/31','upstream_commit':'43e0919ae5b693c1d3c1e8828b74bb774ef92ee0','upstream_folder':'submissions/goose-epoll-xeonfx','original_file_count':len(original_files),'reference_file_count':len(list(source.iterdir())),'status':'PREPARED_UNBUILT','original_license_git_blob':'312b0edf8358f33994a4dc29fc517a3a85f9ab92','original_license_sha256':hashlib.sha256(license_path.read_bytes()).hexdigest(),'protected_byte_identical_files':list(protected),'native_json_hmac':False,'article_batching':False,'gcc_flags_match_candidate':True,'files':rows}
(here/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
(here/'changes.patch').write_text(''.join(patch))
(here/'original-source-sha256.txt').write_text(''.join(f"{hashlib.sha256((original/n).read_bytes()).hexdigest()}  {n}\n" for n in original_files))
(here/'reference-source-sha256.txt').write_text(''.join(f"{hashlib.sha256((source/n).read_bytes()).hexdigest()}  {n}\n" for n in sorted(p.name for p in source.iterdir() if p.is_file())))
print(json.dumps({'status':record['status'],'source':str(source),'original_files':17,'reference_files':record['reference_file_count'],'changed':[r['path'] for r in rows if r['status']!='unchanged'],'byte_identical_protected':list(protected)}))
