#!/usr/bin/env python3
"""Owned-fixture HTTP/PG admission probe; optional transparent PG-wire observer.

Never builds or starts the app. Root schedules the observer/app/probe. For a
strong cap1 test start the observer, point one worker/reader at its listen port,
then run the probe with the observer's --wire-log. HTTP-only coverage is labeled.
"""
import argparse
import asyncio
import base64
import collections
import concurrent.futures
import contextlib
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import threading
import time
import urllib.parse
import uuid


def digest(data):
    return hashlib.sha256(data).hexdigest()


def array_hashes(raw):
    """Read PG's documented binary int8[]/text[] representation, not app state."""
    if len(raw) < 20:
        return []
    ndim, nulls, oid, count, lower = struct.unpack('!iiiii',raw[:20])
    if ndim != 1 or nulls not in (0,1) or oid not in (20,25) or not 0 <= count <= 4096:
        return []
    out, at = [],20
    for _ in range(count):
        if at+4 > len(raw):
            return []
        n = struct.unpack('!i',raw[at:at+4])[0]; at += 4
        if n == -1:
            continue
        if n < 0 or at+n > len(raw):
            return []
        out.append(digest(raw[at:at+n])); at += n
    return out if at == len(raw) else []


def bind_record(body):
    at = body.index(0)+1
    end = body.index(0,at)
    statement = body[at:end].decode('ascii'); at = end+1
    formats = struct.unpack('!H',body[at:at+2])[0]; at += 2+2*formats
    count = struct.unpack('!H',body[at:at+2])[0]; at += 2
    params, elements = [],[]
    for _ in range(count):
        n = struct.unpack('!i',body[at:at+4])[0]; at += 4
        if n == -1:
            params.append(None); continue
        if n < 0 or at+n > len(body):
            raise ValueError('invalid Bind parameter length')
        raw = body[at:at+n]; at += n
        params.append(digest(raw)); elements.extend(array_hashes(raw))
    return {'statement':statement,'parameter_sha256':params,
            'array_element_sha256':elements}


async def proxy(args):
    if not args.wire_log or not args.ready:
        raise ValueError('observer requires --wire-log and --ready')
    if args.wire_log.exists() or args.ready.exists():
        raise FileExistsError('preserve earlier observer artifacts')
    args.wire_log.parent.mkdir(parents=True,exist_ok=True)
    args.ready.parent.mkdir(parents=True,exist_ok=True)
    upstream = urllib.parse.urlsplit(args.database_url)
    host,port = args.listen.rsplit(':',1)
    counter, tasks = 0,set()
    with args.wire_log.open('x',buffering=1) as log:
        def event(kind,**fields):
            log.write(json.dumps({'event':kind,'monotonic':time.monotonic(),**fields})+'\n')

        async def connection(client_read,client_write):
            nonlocal counter
            counter += 1; cid = counter
            pending, outstanding, executions = collections.deque(),0,0
            startup, writer = True,False
            pg_write = None
            buffers = {'front':bytearray(),'back':bytearray()}

            def inspect(direction,chunk):
                nonlocal startup,writer,outstanding,executions
                b = buffers[direction]; b.extend(chunk)
                while True:
                    if direction == 'front' and startup:
                        if len(b)<4: return
                        n = struct.unpack('!I',b[:4])[0]
                        if not 8 <= n <= 32*1024*1024: raise ValueError('invalid startup length')
                        if len(b)<n: return
                        packet=bytes(b[:n]); del b[:n]
                        if struct.unpack('!I',packet[4:8])[0] != 196608:
                            raise ValueError('observer supports plaintext PGv3 startup only')
                        parts=packet[8:].rstrip(b'\0').split(b'\0')
                        settings=dict(zip(parts[::2],parts[1::2]))
                        writer=b'lock_timeout' in settings
                        startup=False
                        event('connection',connection=cid,writer=writer)
                        continue
                    if len(b)<5: return
                    n=struct.unpack('!I',b[1:5])[0]+1
                    if not 5 <= n <= 32*1024*1024: raise ValueError('invalid PG frame length')
                    if len(b)<n: return
                    kind=chr(b[0]); body=bytes(b[5:n]); del b[:n]
                    if direction=='front':
                        if kind=='B': event('bind',connection=cid,writer=writer,**bind_record(body))
                        elif kind=='E': executions+=1
                        elif kind=='S':
                            query=executions>0; pending.append((query,executions))
                            if query:
                                outstanding+=1
                                event('sync',connection=cid,writer=writer,executions=executions,outstanding=outstanding)
                            executions=0
                    elif kind=='Z' and pending:
                        query,count=pending.popleft()
                        if query:
                            outstanding-=1
                            event('ready',connection=cid,writer=writer,executions=count,outstanding=outstanding)

            async def pipe(reader,writer,direction):
                while True:
                    chunk=await reader.read(65536)
                    if not chunk: return
                    inspect(direction,chunk)
                    writer.write(chunk); await writer.drain()

            pumps=[]
            try:
                pg_read,pg_write=await asyncio.open_connection(upstream.hostname or '127.0.0.1',upstream.port or 5432)
                pumps=[asyncio.create_task(pipe(client_read,pg_write,'front')),
                       asyncio.create_task(pipe(pg_read,client_write,'back'))]
                done,_=await asyncio.wait(pumps,return_when=asyncio.FIRST_COMPLETED)
                for task in done: task.result()
            except Exception as error:
                event('observer_error',connection=cid,error=type(error).__name__+': '+str(error))
            finally:
                for task in pumps: task.cancel()
                await asyncio.gather(*pumps,return_exceptions=True)
                for stream in [client_write,pg_write]:
                    if stream:
                        stream.close()
                        with contextlib.suppress(Exception): await stream.wait_closed()
                event('closed',connection=cid,writer=writer,outstanding=outstanding)

        def accept(reader,writer):
            task=asyncio.create_task(connection(reader,writer)); tasks.add(task)
            task.add_done_callback(tasks.discard)
        server=await asyncio.start_server(accept,host,int(port))
        address=server.sockets[0].getsockname()
        args.ready.write_text(json.dumps({'ready':True,'listen_host':address[0],
                                        'listen_port':address[1],'wire_log':str(args.wire_log)})+'\n')
        print(json.dumps({'ready':True,'listen_host':address[0],'listen_port':address[1]}),flush=True)
        stop=asyncio.Event()
        for sig in [signal.SIGINT,signal.SIGTERM]:
            asyncio.get_running_loop().add_signal_handler(sig,stop.set)
        await stop.wait()
        server.close(); await server.wait_closed()
        for task in list(tasks): task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        event('observer_stopped',connections=counter)


class Request:
    def __init__(self,base,method,path,auth=None,body=None,timeout=12):
        self.method,self.path,self.started=method,path,time.monotonic()
        url=urllib.parse.urlsplit(base)
        if url.scheme!='http': raise ValueError('fixture probe requires HTTP')
        self.sock=socket.create_connection((url.hostname,url.port or 80),timeout=timeout)
        self.sock.settimeout(timeout)
        data=json.dumps(body).encode() if body is not None else b''
        headers=[method+' '+path+' HTTP/1.1','Host: '+url.netloc,
                 'Connection: keep-alive','Content-Type: application/json',
                 'Content-Length: '+str(len(data))]
        if auth: headers.append('Authorization: Token '+auth)
        self.sock.sendall(('\r\n'.join(headers)+'\r\n\r\n').encode()+data)

    def waiting(self):
        return not select.select([self.sock],[],[],0)[0]

    def abort(self,rst=False):
        if rst:
            with contextlib.suppress(OSError): self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
        else:
            with contextlib.suppress(OSError): self.sock.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError): self.sock.close()

    def finish(self):
        try:
            response=http.client.HTTPResponse(self.sock); response.begin()
            raw=response.read()
            return {'method':self.method,'path':self.path,'status':response.status,
                    'body':json.loads(raw),'started_monotonic':self.started,
                    'complete_monotonic':time.monotonic()}
        finally:
            self.abort()


def probe(args):
    if not args.base or not args.secret or not args.out:
        raise ValueError('probe requires --base, --secret and --out (or BASE/JWT_SECRET)')
    if args.out.exists(): raise FileExistsError('preserve prior probe output')
    url=urllib.parse.urlsplit(args.database_url)
    if url.scheme not in ('postgres','postgresql'):
        raise ValueError('fixture DATABASE_URL must use postgres:// or postgresql://')
    pg=os.environ.copy(); pg['PGDATABASE']=urllib.parse.unquote(url.path.lstrip('/'))
    pg.pop('PGSERVICE',None)
    pg['PGCONNECT_TIMEOUT']='5'
    if not pg['PGDATABASE'].startswith('mc_pair_'):
        raise ValueError('requires an owned disposable mc_pair_ fixture database')
    for key,value in [('PGHOST',url.hostname),('PGPORT',str(url.port or 5432)),
                      ('PGUSER',urllib.parse.unquote(url.username or '')),
                      ('PGPASSWORD',urllib.parse.unquote(url.password or ''))]:
        if value and key not in pg: pg[key]=value
    pg['PGAPPNAME']='reader_admission_fixture'
    pg['PGOPTIONS']=pg.get('PGOPTIONS','')+' -c statement_timeout=8000 -c lock_timeout=2000'
    command=['psql','-X','-A','-t','-q','-v','ON_ERROR_STOP=1','-d',pg['PGDATABASE']]
    nonce='ra_probe_'+uuid.uuid4().hex
    owner,viewer,tag=nonce+'_owner',nonce+'_viewer',nonce+'_tag'
    slugs=[nonce+'_gate',nonce+'_replacement',nonce+'_write']
    record={'scope':'Owned correctness fixture only; not capacity/performance evidence',
            'database':pg['PGDATABASE'],'base':args.base,'nonce':nonce,'pass':False,
            'wire_observed':bool(args.wire_log),'checks':[],'events':[],
            'configured_expected_readers':args.expected_readers,
            'configured_expected_read_groups':args.expected_read_groups}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    gate=None; fixture=False; requests=[]; flood_stop=threading.Event(); flood_threads=[]; flood=[]

    def save():
        temp=args.out.with_name(args.out.name+'.tmp')
        temp.write_text(json.dumps(record,indent=2)+'\n'); temp.replace(args.out)
    def check(name,condition,**details):
        record['checks'].append({'check':name,'pass':bool(condition),**details}); save()
        if not condition: raise AssertionError(name)
    def quote(text): return "'"+text.replace("'","''")+"'"
    def sql(text):
        result=subprocess.run(command+['-c',text],env=pg,text=True,capture_output=True,timeout=12)
        if result.returncode: raise RuntimeError(result.stderr)
        return result.stdout.strip()
    def token(uid):
        enc=lambda obj:base64.urlsafe_b64encode(json.dumps(obj,separators=(',',':')).encode()).rstrip(b'=')
        now=int(time.time())
        text=enc({'alg':'HS256','typ':'JWT'})+b'.'+enc({'sub':str(uid),'iat':now,'exp':now+600})
        return (text+b'.'+base64.urlsafe_b64encode(hmac.digest(args.secret.encode(),text,'sha256')).rstrip(b'=')).decode()
    def start(method,path,auth=None,body=None):
        request=Request(args.base,method,path,auth,body); requests.append(request); return request
    def api(method,path,auth=None,body=None): return start(method,path,auth,body).finish()
    def wire():
        if not args.wire_log: return [],b''
        raw=args.wire_log.read_bytes(); rows=[]
        for line in raw.splitlines(keepends=True):
            if not line.endswith(b'\n'): break
            rows.append(json.loads(line))
        return rows,raw
    def until(predicate,message,seconds=8):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=predicate()
            if value: return value
            time.sleep(.025)
        raise TimeoutError(message)
    def send_gate(text): gate.stdin.write(text+'\n'); gate.stdin.flush()
    def marker(want):
        end=time.monotonic()+8
        while time.monotonic()<end:
            if gate.poll() is not None: raise RuntimeError('fixture transaction exited: '+gate.stderr.read())
            ready,_,_=select.select([gate.stdout],[],[],.1)
            if ready and gate.stdout.readline().strip()==want: return
        raise TimeoutError('missing transaction marker '+want)
    def finish_all(items,seconds=12):
        executor=concurrent.futures.ThreadPoolExecutor(max_workers=64)
        futures=[executor.submit(r.finish) for r in items]
        done,pending=concurrent.futures.wait(futures,timeout=seconds)
        if pending:
            for r in items: r.abort()
        executor.shutdown(wait=True,cancel_futures=True)
        if pending: raise TimeoutError('HTTP drain exceeded bounded deadline')
        return [f.result() for f in futures]

    save()
    try:
        hash_value='$2a$10$ZSfEoPvlcsj2XfvsSeK25em4NZ9Jm7ntGqXuLgQfHEeZPYB8899wq'
        sql('BEGIN; '+''.join('INSERT INTO users(username,email,password_hash) VALUES('+quote(name)+','+quote(name+'@example.com')+','+quote(hash_value)+');' for name in [owner,viewer])+
            ''.join('INSERT INTO articles(slug,author_id,title,description,body) SELECT '+quote(slug)+',id,'+quote(slug)+",'fixture',"+quote('body:'+slug)+' FROM users WHERE username='+quote(owner)+';' for slug in slugs)+
            'INSERT INTO tags(name) VALUES('+quote(tag)+'); INSERT INTO article_tags(article_id,tag_id) SELECT a.id,t.id FROM articles a CROSS JOIN tags t WHERE a.slug IN('+','.join(quote(x) for x in slugs)+') AND t.name='+quote(tag)+'; '+
            'INSERT INTO follows(follower_id,followee_id) SELECT v.id,o.id FROM users v,users o WHERE v.username='+quote(viewer)+' AND o.username='+quote(owner)+'; '+
            'INSERT INTO favorites(user_id,article_id) SELECT v.id,a.id FROM users v,articles a WHERE v.username='+quote(viewer)+' AND a.slug='+quote(slugs[1])+'; COMMIT;')
        fixture=True
        ids=json.loads(sql("SELECT json_build_object('owner',(SELECT id FROM users WHERE username="+quote(owner)+"),'viewer',(SELECT id FROM users WHERE username="+quote(viewer)+"),'write',(SELECT id FROM articles WHERE slug="+quote(slugs[2])+"))"))
        auth,view=token(ids['owner']),token(ids['viewer'])
        check('fixture_preflight',api('GET','/api/articles/'+slugs[0])['body']['article']['body']=='body:'+slugs[0])
        gate=subprocess.Popen(command,env=pg,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        send_gate("BEGIN; LOCK TABLE tags IN ACCESS EXCLUSIVE MODE; SELECT 'LOCK_HELD';")
        marker('LOCK_HELD')
        fill_count=args.expected_readers*args.expected_read_groups*4*args.batch+32
        if fill_count>1024: raise ValueError('use a small isolated fixture configuration (prefer1worker/1reader/cap1)')
        fillers=[start('GET','/api/articles/'+slugs[0]) for _ in range(fill_count)]
        def lock_witness():
            value=sql("SELECT coalesce(json_agg(json_build_object('pid',pid,'wait',wait_event,'query',query)), '[]'::json) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND wait_event_type='Lock'")
            rows=json.loads(value)
            return rows if len(rows)>=args.expected_readers else None
        witness=until(lock_witness,'readers did not block on the held relation')
        record['events'].append({'event':'readers blocked on fixture tag lock','witness':witness})
        if args.wire_log:
            def cap_full():
                rows,_=wire(); state={}
                for row in rows:
                    if row['event'] in ('sync','ready') and not row.get('writer'):
                        state[row['connection']]=row['outstanding']
                return state if len(state)==args.expected_readers and all(n==args.expected_read_groups for n in state.values()) else None
            check('wire_witness_reader_cap_filled',bool(until(cap_full,'wire reader cap not filled')))
        else:
            record['coverage_limit']='HTTP/DB only: cap and abandoned Bind absence are not proven without --wire-log'
            time.sleep(.2)
        abandoned_slugs=[nonce+'_abandon_'+str(i) for i in range(args.abandon_count)]
        abandoned=[start('GET','/api/articles/'+s,auth) for s in abandoned_slugs]
        check('event_loop_live_while_readers_gated',api('GET','/__reader_admission_marker__')['status']==404)
        time.sleep(.1)
        for r in abandoned: r.abort(rst=True)
        replacements=[start('GET','/api/articles/'+slugs[1],view) for _ in abandoned]
        favorite=start('POST','/api/articles/'+slugs[2]+'/favorite',auth)
        until(lambda:sql(f"SELECT count(*) FROM favorites WHERE article_id={ids['write']} AND user_id={ids['owner']}")=='1','favorite did not commit while readers gated')
        title=nonce+' updated'; new_body='updated:'+nonce
        update=start('PUT','/api/articles/'+slugs[2],auth,{'article':{'title':title,'body':new_body}})
        def updated_slug():
            return sql('SELECT slug FROM articles WHERE id='+str(ids['write'])+' AND title='+quote(title))
        new_slug=until(updated_slug,'UPDATE did not commit while readers gated')
        check('postcommit_responses_wait_for_reader_admission',favorite.waiting() and update.waiting())
        comment_body='exactly-once:'+nonce
        comment=api('POST','/api/articles/'+new_slug+'/comments',auth,{'comment':{'body':comment_body}})
        check('independent_writer_responds_while_readers_gated',comment['status']==201 and comment['body']['comment']['body']==comment_body)
        old_paths=[('/api/articles?limit=10','list-all'),('/api/articles?tag='+tag,'list-tag'),
                   ('/api/articles?author='+owner,'list-author'),('/api/articles?favorited='+viewer,'list-favorited'),
                   ('/api/articles/feed?limit=10','feed'),('/api/articles/'+slugs[1],'article'),
                   ('/api/articles/'+new_slug+'/comments','comments'),('/api/tags','tags'),
                   ('/api/profiles/'+owner,'direct-profile')]
        older=[start('GET',path,view) for path,_ in old_paths]
        def flooding(index):
            path='/api/profiles/'+owner if index%3==0 else '/api/articles?author='+owner
            completed=0; error=None
            try:
                while not flood_stop.is_set() and completed<64:
                    r=Request(args.base,'GET',path,view,timeout=8)
                    result=r.finish()
                    if result['status']!=200: raise AssertionError('flood request status '+str(result['status']))
                    completed+=1
            except Exception as exc:
                error=type(exc).__name__+': '+str(exc)
            flood.append({'class':'direct' if index%3==0 else 'pooled','completed':completed,'error':error})
        for index in range(48):
            t=threading.Thread(target=flooding,args=(index,),daemon=True); t.start(); flood_threads.append(t)
        check('gate_still_blocks_original_reads',all(r.waiting() for r in fillers[:8]))
        send_gate("COMMIT; SELECT 'RELEASED';"); marker('RELEASED')
        record['events'].append({'event':'reader gate released','monotonic':time.monotonic()})
        old_results=finish_all(older)
        check('all_old_direct_and_pooled_families_progress_under_arrivals',all(r['status']==200 for r in old_results),responses=old_results)
        for (path,kind),response in zip(old_paths,old_results):
            body=response['body']
            if kind=='article': check('new_generation_article_flags',body['article']['slug']==slugs[1] and body['article']['favorited'] is True and body['article']['author']['following'] is True)
            elif kind=='comments': check('comment_seen_once',sum(c['body']==comment_body for c in body['comments'])==1)
            elif kind=='tags': check('fixture_tag_visible',tag in body['tags'])
            elif kind=='direct-profile': check('direct_profile_metadata',body['profile']['username']==owner and body['profile']['following'] is True)
            elif kind in ('list-author','list-tag','feed'): check(kind+'_count',body['articlesCount']==3)
            elif kind=='list-favorited': check('favorited_viewer_isolated',body['articlesCount']==1 and body['articles'][0]['slug']==slugs[1])
        fresh=finish_all([favorite,update])
        check('fresh_postcommit_metadata_after_queue_drain',all(r['status']==200 and r['body']['article']['slug']==new_slug and r['body']['article']['title']==title and r['body']['article']['body']==new_body and r['body']['article']['favoritesCount']==1 and r['body']['article']['favorited'] is True for r in fresh),responses=fresh)
        replaced=finish_all(replacements)
        check('rapid_slot_reuse_returns_only_replacement_bodies',all(r['status']==200 and r['body']['article']['slug']==slugs[1] and r['body']['article']['body']=='body:'+slugs[1] and r['body']['article']['favorited'] is True for r in replaced))
        filled=finish_all(fillers)
        check('submitted_original_reads_not_dropped',all(r['status']==200 and r['body']['article']['slug']==slugs[0] for r in filled))
        flood_stop.set()
        for t in flood_threads: t.join(timeout=9)
        check('mixed_arrival_workers_complete',all(not t.is_alive() for t in flood_threads) and not any(x['error'] for x in flood) and sum(x['completed'] for x in flood if x['class']=='direct')>0 and sum(x['completed'] for x in flood if x['class']=='pooled')>0,flood=flood)
        check('writer_effects_exactly_once',sql('SELECT count(*) FROM comments WHERE body='+quote(comment_body))=='1' and sql(f"SELECT count(*) FROM favorites WHERE article_id={ids['write']} AND user_id={ids['owner']}")=='1')
        if args.wire_log:
            rows,raw=wire(); binds=[x for x in rows if x['event']=='bind']; syncs=[x for x in rows if x['event']=='sync' and not x.get('writer')]
            hashes={h for x in binds for h in x['parameter_sha256']+x['array_element_sha256'] if h}
            check('abandoned_unsubmitted_slugs_never_bound',not any(digest(s.encode()) in hashes for s in abandoned_slugs))
            check('wire_reader_group_cap_and_sync4',bool(syncs) and all(x['outstanding']<=args.expected_read_groups and x['executions']<=4 for x in syncs),max_outstanding=max(x['outstanding'] for x in syncs),max_executions=max(x['executions'] for x in syncs))
            check('wire_read_group_boundary_exercised',any(x['executions']==4 for x in syncs))
            for statement in ['s19','s17']:
                matches=[x for x in binds if x.get('writer') and x['statement']==statement and digest(slugs[2].encode()) in x['parameter_sha256']]
                check(statement+'_mutation_submitted_once',len(matches)==1,count=len(matches))
            check('wire_observer_no_parse_errors',not any(x['event']=='observer_error' for x in rows))
            record['wire_receipt']={'path':str(args.wire_log),'observed_prefix_bytes':len(raw),'observed_prefix_sha256':digest(raw),'complete_records':len(rows)}
        record['pass']=True
    except BaseException as error:
        record['error']=type(error).__name__+': '+str(error)
    finally:
        flood_stop.set()
        for request in requests: request.abort()
        for t in flood_threads: t.join(timeout=9)
        if gate is not None:
            with contextlib.suppress(Exception):
                send_gate('ROLLBACK;'); gate.stdin.close(); gate.wait(timeout=3)
            if gate.poll() is None:
                gate.terminate(); gate.wait(timeout=3)
            record['gate_stderr']=gate.stderr.read()
        if fixture:
            try:
                sql('BEGIN; DELETE FROM articles WHERE author_id IN(SELECT id FROM users WHERE username='+quote(owner)+'); DELETE FROM users WHERE username IN('+quote(owner)+','+quote(viewer)+'); DELETE FROM tags WHERE name='+quote(tag)+'; COMMIT;')
                record['fixture_cleaned']=sql('SELECT count(*) FROM users WHERE username IN('+quote(owner)+','+quote(viewer)+')')=='0' and sql('SELECT count(*) FROM tags WHERE name='+quote(tag))=='0'
                if not record['fixture_cleaned']: record['pass']=False
            except Exception as error:
                record.update({'pass':False,'cleanup_error':type(error).__name__+': '+str(error)})
        record['finished_unix_s']=time.time(); save()
    print(json.dumps({k:record.get(k) for k in ['pass','wire_observed','fixture_cleaned','error','cleanup_error']}))
    return 0 if record['pass'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default=os.environ.get('BASE'))
    parser.add_argument('--database-url',default=os.environ.get('DATABASE_URL'))
    parser.add_argument('--secret',default=os.environ.get('JWT_SECRET'))
    parser.add_argument('--out',type=Path)
    parser.add_argument('--wire-log',type=Path)
    parser.add_argument('--expected-readers',type=int,default=1)
    parser.add_argument('--expected-read-groups',type=int,default=1)
    parser.add_argument('--batch',type=int,default=32)
    parser.add_argument('--abandon-count',type=int,default=24)
    parser.add_argument('--proxy',action='store_true')
    parser.add_argument('--listen',default='127.0.0.1:15432')
    parser.add_argument('--ready',type=Path)
    args=parser.parse_args()
    if not args.database_url: parser.error('DATABASE_URL/--database-url is required')
    if min(args.expected_readers,args.expected_read_groups,args.batch,args.abandon_count)<1:
        parser.error('fixture counts must be positive; cap0 is not a bounded-cap probe')
    if args.proxy: asyncio.run(proxy(args)); return 0
    return probe(args)


if __name__=='__main__':
    raise SystemExit(main())
