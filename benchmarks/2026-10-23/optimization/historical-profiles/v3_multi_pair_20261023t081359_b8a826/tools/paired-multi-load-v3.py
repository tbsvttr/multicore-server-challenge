#!/usr/bin/env python3
"""Prepare or execute a separate fixed80k-user, four-shard ARM64/Docker comparison.

Default is a network-free dry plan. --execute requires an existing frozen plan.
"""
import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import threading
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--config')
p.add_argument('--plan',required=True)
p.add_argument('--execute',action='store_true')
a=p.parse_args()
planfile=pathlib.Path(a.plan)

def write_json(path,obj):
    pathlib.Path(path).write_text(json.dumps(obj,indent=2)+'\n')

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

if not a.execute:
    if not a.config: p.error('--config is required to prepare a plan')
    cfg=json.loads(pathlib.Path(a.config).read_text())
    assert len(cfg['cases'])==2,'the initial protocol is exactly two cases and three pairs'
    users=cfg.get('users',80000)
    assert users==80000,'this separate protocol is capped at exactly80k users; no rescaling'
    for case in cfg['cases']:
        assert case['name'].replace('_','').isalnum() and len(case['name'])<=20
        assert case['binary'].startswith('/') and case['source_dir'].startswith('/')
    assert cfg['cases'][0]['name']!=cfg['cases'][1]['name']
    scope='local ARM64 Mac/Docker80k-user four-shard fixed-load comparison; not an official score or capacity search'
    order=[[0,1],[1,0],[0,1]]
    ramp,measure,tail=60,60,15
    shards=[{'box_index':i,'users':20000,'id_offset':i*20000,'host':'127.0.0.'+str(i+1)} for i in range(4)]
    plan={'controller':'paired-multi-load-v3','scope':scope,
          'configuration':cfg,'configuration_sha256':sha(a.config),
          'protocol':{'users':users,'articles':500000,'think_scale':1.0,'ramp_s':ramp,'measure_s':measure,'tail_s':tail,
                      'pairs':3,'order':order,'fresh_full_seed_per_attempt':True,
                      'shards':shards,'gomaxprocs_per_shard':1,'synchronized_start_at':True,
                      'load_cgroup_cpus':4,
                      'app_nofile_minimum':200000,'actual_app_uid_and_limits_required':True,
                      'launch_wrapper':'runuser -u challenge -- prlimit --nofile=200000:200000 -- binary',
                      'load_cgroup_cpu_limit_pct':75.0,
                      'paired_random_stream':'same native run-id and VU ids within each pair; fresh DBs prevent name collisions',
                      'warmup':'none; this is a fixed-load diagnostic, not the official warmup/search/hold protocol',
                      'invalid_policy':'native lg_limited or failed infrastructure is INVALID; retain, never replace',
                      'interpretation':'at fixed unsaturated load, compare latency/CPU; similar req/s cannot establish capacity'},
          'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    if planfile.exists(): raise FileExistsError('refusing to replace an existing plan')
    write_json(planfile,plan)
    attempts=sum(map(len,order))
    print(json.dumps({'dry_plan':str(planfile),'attempts':attempts,'users':users,'minimum_load_seconds':attempts*(ramp+measure+tail),
                      'execution':'explicit --execute required; no Docker commands were run'}))
    raise SystemExit

plan=json.loads(planfile.read_text())
cfg=plan['configuration'];protocol=plan['protocol']
assert plan['controller']=='paired-multi-load-v3'
assert protocol['load_cgroup_cpus']==4
assert protocol['users']==80000 and protocol['gomaxprocs_per_shard']==1
assert protocol['shards']==[{'box_index':i,'users':20000,'id_offset':i*20000,'host':'127.0.0.'+str(i+1)} for i in range(4)]
assert (protocol['ramp_s'],protocol['measure_s'],protocol['tail_s'])==(60,60,15)
hostroot=pathlib.Path(cfg.get('host_evidence','/private/tmp/multicore-research-20261022')).resolve()
target=cfg.get('target_container','multicore-goose-dev-20261022')
stamp=time.strftime('%Y%m%dT%H%M%S',time.gmtime()).lower()
runname='v3_multi_pair_'+stamp+'_'+os.urandom(3).hex()
root=hostroot/'paired-multi-load-v3'/runname
root.mkdir(parents=True,exist_ok=False)
container_root='/evidence/paired-multi-load-v3/'+runname
toolroot=root/'tools'
toolroot.mkdir()
for tool in ['lab-target-control-v2.py','lab-monitor.py','paired-multi-load-v3.py']:
    shutil.copy2(hostroot/tool,toolroot/tool)
target_helper=container_root+'/tools/lab-target-control-v2.py'
monitor_helper=container_root+'/tools/lab-monitor.py'
write_json(root/'frozen-tool-sha256.json',{tool:sha(toolroot/tool) for tool in
    ['lab-target-control-v2.py','lab-monitor.py','paired-multi-load-v3.py']})
loadname='multicore-multi-load-'+runname.replace('_','-')
write_json(root/'plan.json',plan)
(root/'plan.sha256').write_text(sha(planfile)+'\n')
events=(root/'events.jsonl').open('x')
load_created=False
host_stop=threading.Event()

def event(name,**data):
    row={'event':name,'wall_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),**data}
    events.write(json.dumps(row)+'\n');events.flush()
    print(json.dumps(row),flush=True)

def command(argv,save=None,allowed=(0,),timeout=180):
    r=subprocess.run(argv,text=True,capture_output=True,timeout=timeout)
    if save:
        pathlib.Path(save).write_text(r.stdout+r.stderr)
    if r.returncode not in allowed:
        raise RuntimeError(f'command exited{r.returncode}: {argv!r}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')
    return r

def docker(*argv,**kw):
    return command(['docker',*argv],**kw)

def control(action,out,*argv,**kw):
    return docker('exec','--user','root',target,'python3',target_helper,action,'--out',out,*argv,**kw)

def inspect(name,path):
    obj=json.loads(docker('inspect',name).stdout)[0]
    write_json(path,obj)
    return obj

def assert_budget(obj,cpus,memory):
    h=obj['HostConfig']
    assert h['NanoCpus']==cpus*10**9 and h['Memory']==memory and h['MemorySwap']==memory,h
    assert not h['CpusetCpus'],'explicit CPU affinity is forbidden'

def host_monitor():
    with (root/'host-memory.jsonl').open('x') as out:
        tick=0
        while not host_stop.is_set():
            at=time.monotonic()
            row={'wall_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns()}
            for name,argv in [('vm_stat',['vm_stat']),('swapusage',['sysctl','vm.swapusage'])]:
                try:
                    r=subprocess.run(argv,text=True,capture_output=True,timeout=3)
                    row[name]={'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
                except Exception as e: row[name]={'error':str(e)}
            if tick%10==0:
                try:
                    r=subprocess.run(['memory_pressure','-Q'],text=True,capture_output=True,timeout=3)
                    row['memory_pressure']={'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
                except Exception as e: row['memory_pressure']={'error':str(e)}
            out.write(json.dumps(row)+'\n');out.flush();tick+=1
            host_stop.wait(max(0.05,1-(time.monotonic()-at)))

def start_monitor(container,path,app_pgid=-1):
    docker('exec','--user','root','-d',container,'python3',monitor_helper,'--out',path+'.jsonl',
           '--stop',path+'.stop','--app-pgid',str(app_pgid))

def summarize_monitor(path,start_ms,end_ms,quota):
    rows=[json.loads(line) for line in pathlib.Path(path).read_text().splitlines()]
    if not rows or end_ms<=start_ms:return {'valid_sampling':False,'error':'empty witness or invalid window'}
    monotonic_order=all(b['monotonic_ns']>x['monotonic_ns'] for x,b in zip(rows,rows[1:]))
    wall_order=all(b['wall_ns']>=x['wall_ns'] for x,b in zip(rows,rows[1:]))
    if not monotonic_order or not wall_order:
        return {'valid_sampling':False,'error':'witness timestamps are not ordered','monotonic_order':monotonic_order,'wall_order':wall_order}
    # Include the nearest sample outside either boundary when available. This
    # exposes gaps straddling a boundary instead of checking only inner samples.
    left=[i for i,r in enumerate(rows) if r['wall_ns']/10**6<=start_ms]
    right=[i for i,r in enumerate(rows) if r['wall_ns']/10**6>=end_ms]
    lo=left[-1] if left else 0
    hi=right[0] if right else len(rows)-1
    span=rows[lo:hi+1]
    start_missing=max(0,span[0]['wall_ns']/10**6-start_ms)/1000
    end_missing=max(0,end_ms-span[-1]['wall_ns']/10**6)/1000
    mono_gaps=[(b['monotonic_ns']-x['monotonic_ns'])/10**9 for x,b in zip(span,span[1:])]
    wall_gaps=[(b['wall_ns']-x['wall_ns'])/10**9 for x,b in zip(span,span[1:])]
    coverage={'measurement_start_ms':start_ms,'measurement_end_ms':end_ms,
              'coverage_span_samples':len(span),'coverage_start_missing_s':start_missing,
              'coverage_end_missing_s':end_missing,'full_window_bracketed':bool(left and right),
              'max_sample_gap_s':max(mono_gaps,default=None),
              'max_wall_sample_gap_s':max(wall_gaps,default=None)}
    selected=[r for r in rows if start_ms<=r['wall_ns']/10**6<=end_ms]
    if len(selected)<2:return {'valid_sampling':False,'samples':len(selected),**coverage}
    first,last=selected[0],selected[-1]
    elapsed=(last['monotonic_ns']-first['monotonic_ns'])/10**9
    cpu=(last['cpu']['usage_usec']-first['cpu']['usage_usec'])/10**6
    out={'samples':len(selected),'elapsed_s':elapsed,'cgroup_cpu_quota_pct':cpu/elapsed/quota*100,
         'cpu_scope':'sampled interval inside the measurement window',
         'sampled_interval_start_ms':first['wall_ns']/10**6,'sampled_interval_end_ms':last['wall_ns']/10**6,
         'memory_peak_sampled_bytes':max(int(r['memory.current']) for r in selected),
         'swap_peak_sampled_bytes':max(int(r['memory.swap.current']) for r in selected),
         'memory_events_before':first['memory.events'],'memory_events_after':last['memory.events']}
    out.update(coverage)
    out['valid_sampling']=(start_missing<=3 and end_missing<=3 and out['max_sample_gap_s']<=3
                           and out['max_wall_sample_gap_s']<=3 and cpu>=0)
    for kind in ['app','pg']:
        out[kind+'_whole_target_pct']=(last[kind]['cpu_s']-first[kind]['cpu_s'])/elapsed/8*100
        out[kind+'_rss_sum_peak_bytes']=max(r[kind]['rss_bytes'] for r in selected)
    return out

def memory_event_counts(text):
    return {key:int(value) for key,value in (line.split() for line in text.splitlines())}

def actual_app_limits_valid(witness,expected_uid):
    if not isinstance(witness,dict) or witness.get('valid') is not True:return False
    processes=witness.get('processes',[])
    if len(processes)!=1:return False
    proc=processes[0]
    enough=lambda value:value=='unlimited' or isinstance(value,int) and value>=200000
    return (isinstance(proc.get('pid'),int) and proc['pid']>0 and proc.get('uid')==expected_uid
            and proc.get('uids')==[expected_uid]*4
            and enough(proc.get('nofile_soft')) and enough(proc.get('nofile_hard')))

def assess_target_runtime(before,after):
    result={'valid_witness':False,'pass':False,'reasons':[]}
    if not isinstance(after.get('app_healthy'),bool):
        result['reasons'].append('after-load app health witness is missing')
        return result
    try:
        old=memory_event_counts(before['memory.events'])
        new=memory_event_counts(after['memory.events'])
        if not {'oom','oom_kill'}<=old.keys() or not {'oom','oom_kill'}<=new.keys():
            raise ValueError('OOM counter keys are missing')
        deltas={name:new.get(name,0)-old.get(name,0) for name in ['oom','oom_kill','oom_group_kill']}
        if any(value<0 for value in deltas.values()):raise ValueError('OOM counters moved backwards')
    except (KeyError,TypeError,ValueError,AttributeError) as e:
        result['reasons'].append('invalid target OOM witness: '+str(e))
        return result
    result.update(valid_witness=True,app_healthy=after['app_healthy'],oom_deltas=deltas)
    if not after['app_healthy']:result['reasons'].append('app is unhealthy after load and before clean stop')
    if any(deltas.values()):result['reasons'].append('target cgroup recorded OOM events during the attempt')
    result['pass']=not result['reasons']
    return result

attempts=[]
failure=None
try:
    targetobj=inspect(target,root/'target-inspect.json')
    assert_budget(targetobj,8,16*1024**3)
    assert targetobj['State']['Running']
    control('probe-limits',container_root+'/runuser-prlimit-probe.json')
    control('snapshot',container_root+'/target-initial.json')
    initial=json.loads((root/'target-initial.json').read_text())
    low,high=map(int,initial['ip_local_port_range'].split())
    assert all(s['users']<high-low-1024 for s in protocol['shards']),'not enough ports per target address'
    # Refuse an occupied port instead of stopping somebody else's server.
    check="import socket,sys;sys.exit(1 if any(socket.socket().connect_ex(('127.0.0.'+str(i),int(sys.argv[1])))==0 for i in range(1,5)) else 0)"
    docker('exec','--user','root',target,'python3','-c',check,str(cfg.get('port',3000)))
    image=cfg.get('load_image') or targetobj['Image']
    docker('run','-d','--user','root','--name',loadname,'--label','multicore.local.owner='+runname,
           '--cpus',str(protocol['load_cgroup_cpus']),'--memory','4g','--memory-swap','4g','--ulimit','nofile=200000:200000',
           '--network','container:'+target,'--volume',str(hostroot)+':/evidence:rw',
           '--entrypoint','/bin/sh',image,'-c','exec sleep infinity')
    load_created=True
    loadobj=inspect(loadname,root/'load-inspect.json')
    assert_budget(loadobj,protocol['load_cgroup_cpus'],4*1024**3)
    write_json(root/'tool-source-sha256.json',{str(f.relative_to(hostroot)):sha(f) for f in
        [hostroot/'tools/loadgen',hostroot/'lab-monitor.py',hostroot/'lab-target-control-v2.py',hostroot/'paired-multi-load-v3.py']})
    write_json(root/'original-10k-tools-readonly-sha256.json',{n:sha(hostroot/n) for n in
        ['paired-load.py','lab-monitor.py','lab-target-control.py','article-10k-plan.json','article-smoke-plan.json']})
    (root/'frozen').mkdir()
    for case in cfg['cases']:
        casepath=root/(case['name']+'.json')
        write_json(casepath,case)
        control('freeze',container_root+'/frozen/'+case['name'],'--case',container_root+'/'+case['name']+'.json')
        case['metadata']=container_root+'/frozen/'+case['name']+'/metadata.json'
        metadata=json.loads((root/'frozen'/case['name']/'metadata.json').read_text())
        if case.get('expected_binary_sha256'):
            assert metadata['binary_sha256']==case['expected_binary_sha256'],'case binary differs from predeclared hash'
        write_json(casepath,case)
    hostthread=threading.Thread(target=host_monitor,daemon=True);hostthread.start()
    serial=0
    for pair,order in enumerate(protocol['order'],1):
        for case_index in order:
            serial+=1;case=cfg['cases'][case_index]
            name=f'{serial:02d}-p{pair}-{case["name"]}'
            attempt=root/name;attempt.mkdir()
            cdir=container_root+'/'+name
            db='mc_pair_'+stamp.replace('t','_')+'_'+f'{serial:02d}'+'_'+os.urandom(2).hex()
            state={'id':name,'pair':pair,'case':case['name'],'database':db,'classification':'INCOMPLETE'}
            attempts.append(state)
            event('attempt_start',**state)
            processes=[]
            load_logs=[]
            app=None
            try:
                control('clone',cdir+'/database.json','--database',db,timeout=180)
                control('snapshot',cdir+'/before.json')
                control('start',cdir+'/app.json','--database',db,'--case',container_root+'/'+case['name']+'.json',
                        '--port',str(cfg.get('port',3000)),'--secret',cfg.get('jwt_secret','multicore-server-challenge'),timeout=75)
                app=json.loads((attempt/'app.json').read_text())
                assert actual_app_limits_valid(app.get('actual_app'),app['app_uid']),'actual startup app UID/NOFILE witness is invalid'
                control('snapshot',cdir+'/before-load.json','--case',cdir+'/app.json')
                before_load=json.loads((attempt/'before-load.json').read_text())
                state['before_load_actual_app']=before_load.get('actual_app')
                assert before_load.get('app_healthy') is True,'app became unhealthy before load'
                assert actual_app_limits_valid(before_load.get('actual_app'),app['app_uid']),'actual pre-load app UID/NOFILE witness is invalid'
                start_monitor(target,cdir+'/target-monitor',app['pgid'])
                start_monitor(loadname,cdir+'/load-monitor')
                start_ms=int(time.time()*1000)+5000
                all_commands=[]
                for shard in protocol['shards']:
                    idx=shard['box_index']
                    argv=['docker','exec','--user','root','--env','GOMAXPROCS=1',loadname,'/evidence/tools/loadgen','run',
                          '-target','http://'+shard['host']+':'+str(cfg.get('port',3000)),'-users',str(shard['users']),
                          '-ramp','60s','-measure','60s','-tail','15s','-articles','500000','-think-scale','1',
                          '-box-index',str(idx),'-id-offset',str(shard['id_offset']),'-start-at',str(start_ms),
                          '-run-id',runname+'-pair'+str(pair),'-secret',cfg.get('jwt_secret','multicore-server-challenge'),
                          '-out',cdir+'/box'+str(idx)+'.json']
                    all_commands.append(argv)
                    log=(attempt/('box'+str(idx)+'.log')).open('x')
                    load_logs.append(log)
                    processes.append(subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT))
                write_json(attempt/'load-commands.json',all_commands)
                deadline=time.monotonic()+175
                heartbeat=time.monotonic()+15
                while any(proc.poll() is None for proc in processes):
                    if time.monotonic()>deadline:
                        for proc in processes:
                            if proc.poll() is None:proc.terminate()
                        kill="import pathlib,os,signal;[(os.kill(int(p.parent.name),signal.SIGTERM)) for p in pathlib.Path('/proc').glob('[0-9]*/exe') if p.exists() and os.path.realpath(p)=='/evidence/tools/loadgen']"
                        docker('exec','--user','root',loadname,'python3','-c',kill)
                        raise TimeoutError('native four-shard load exceeded175s; owned generators terminated')
                    if time.monotonic()>=heartbeat:
                        event('attempt_running',id=name,active_shards=sum(proc.poll() is None for proc in processes));heartbeat+=15
                    time.sleep(1)
                state['load_exits']=[proc.returncode for proc in processes]
                if any(state['load_exits']):raise RuntimeError('one or more native load clients failed; see all shard logs')
                state['shard_verdicts']=[]
                for shard in protocol['shards']:
                    idx=shard['box_index']
                    raw=json.loads((attempt/('box'+str(idx)+'.json')).read_text())
                    meta=raw['meta']
                    assert meta['start_at_ms']==start_ms and meta['users']==20000 and meta['box_index']==idx and meta['id_offset']==idx*20000,meta
                    assert meta['think_scale']==1 and meta['articles']==500000 and meta['gomaxprocs']==1,meta
                    result=docker('exec','--user','root',loadname,'/evidence/tools/loadgen','merge',
                                  '-o',cdir+'/box'+str(idx)+'-merged.json',cdir+'/box'+str(idx)+'.json',
                                  allowed=(0,3),save=attempt/('box'+str(idx)+'-merged.txt'))
                    shard_result=json.loads((attempt/('box'+str(idx)+'-merged.json')).read_text())
                    state['shard_verdicts'].append({'box_index':idx,'merge_exit':result.returncode,'verdict':shard_result['verdict'],
                                                    'overall':shard_result['overall'],'boxes':shard_result['boxes']})
                merged=docker('exec','--user','root',loadname,'/evidence/tools/loadgen','merge','-o',cdir+'/merged.json',
                              *[cdir+'/box'+str(i)+'.json' for i in range(4)],
                              allowed=(0,3),save=attempt/'merged.txt')
                state['merge_exit']=merged.returncode
                result=json.loads((attempt/'merged.json').read_text())
                assert result['users']==80000 and len(result['boxes'])==4,result
                state.update(verdict=result['verdict'],overall=result['overall'],boxes=result['boxes'])
                state['classification']='INVALID_GENERATOR' if result['verdict']['lg_limited'] else 'PASS' if result['verdict']['pass'] else 'FAIL_SLO'
            except Exception as e:
                state['classification']='INVALID_INFRASTRUCTURE';state['error']=type(e).__name__+': '+str(e)
            finally:
                for log in load_logs:log.close()
                for who in ['target','load']:(attempt/(who+'-monitor.stop')).touch()
                time.sleep(1.2)
                try:
                    raw_files=[attempt/('box'+str(i)+'.json') for i in range(4) if (attempt/('box'+str(i)+'.json')).exists()]
                    if raw_files:
                        raw=json.loads(raw_files[0].read_text());meta=raw['meta']
                        for who,quota in [('target',8),('load',protocol['load_cgroup_cpus'])]:
                            path=attempt/(who+'-monitor.jsonl')
                            if path.exists():
                                state[who+'_monitor']=summarize_monitor(path,meta['window_start_ms'],meta['window_end_ms'],quota)
                            else:
                                state[who+'_monitor']={'valid_sampling':False,'error':'missing witness'}
                        if state['classification']=='PASS' and not all(state[k+'_monitor']['valid_sampling'] for k in ['target','load']):
                            state['classification']='INVALID_MONITOR'
                        lm=state['load_monitor']
                        if lm.get('valid_sampling'):
                            state['load_cgroup_headroom_pass']=lm['cgroup_cpu_quota_pct']<=protocol.get('load_cgroup_cpu_limit_pct',75.0)
                            def mem_events(s):return {k:int(v) for k,v in (line.split() for line in s.splitlines())}
                            before_events,after_events=mem_events(lm['memory_events_before']),mem_events(lm['memory_events_after'])
                            state['load_oom_delta']=after_events.get('oom_kill',0)-before_events.get('oom_kill',0)
                            if not state['load_cgroup_headroom_pass'] or state['load_oom_delta']:
                                state['classification']='INVALID_GENERATOR_CGROUP'
                except Exception as e:
                    state['monitor_error']=str(e)
                    if state['classification']=='PASS':state['classification']='INVALID_MONITOR'
                try:
                    argv=['--case',cdir+'/app.json'] if (attempt/'app.json').exists() else []
                    control('snapshot',cdir+'/after-load.json',*argv)
                    after_load=json.loads((attempt/'after-load.json').read_text())
                    state['after_load_actual_app']=after_load.get('actual_app')
                    expected_uid=app['app_uid'] if app else json.loads((attempt/'app.json').read_text())['app_uid']
                    state['actual_app_limits_valid']=actual_app_limits_valid(after_load.get('actual_app'),expected_uid)
                    state['target_runtime']=assess_target_runtime(json.loads((attempt/'before.json').read_text()),after_load)
                except Exception as e:
                    state['after_snapshot_error']=str(e)
                    state['actual_app_limits_valid']=False
                    state['target_runtime']={'valid_witness':False,'pass':False,'reasons':['after-load snapshot unavailable']}
                if state['classification'] in ['PASS','FAIL_SLO']:
                    if state['target_runtime']['valid_witness'] and not state['target_runtime']['pass']:
                        state['classification']='FAIL_TARGET_RUNTIME'
                    elif not state['actual_app_limits_valid']:
                        state['classification']='INVALID_TARGET_NOFILE'
                    elif state['classification']=='PASS' and not state['target_runtime']['pass']:
                        state['classification']='INVALID_TARGET_WITNESS'
                if (attempt/'app.json').exists():
                    try: control('stop',cdir+'/stopped.json','--case',cdir+'/app.json')
                    except Exception as e: state['stop_error']=str(e)
                try: control('snapshot',cdir+'/after.json')
                except Exception as e: state['after_snapshot_error']=str(e)
                try: control('drop',cdir+'/dropped.json','--database',db)
                except Exception as e: state['database_cleanup_error']=str(e)
                write_json(attempt/'assessment.json',state)
                write_json(root/'attempts.json',attempts)
                event('attempt_complete',id=name,classification=state['classification'])
                if 'stop_error' in state:raise RuntimeError('owned app stop failed; refusing to launch another server')
                # Allow Linux TIME_WAIT to drain without changing sysctls or reusing ports.
                if serial<sum(map(len,protocol['order'])):
                    event('draining_connections',seconds=65)
                    for _ in range(13):time.sleep(5)
    summary={'scope':plan['scope'],'attempts':attempts,'plan_sha256':sha(planfile),'pairs':[]}
    for pair in range(1,len(protocol['order'])+1):
        rows=[r for r in attempts if r['pair']==pair]
        valid=len(rows)==2 and all(r['classification']=='PASS' for r in rows)
        item={'pair':pair,'qualified':valid}
        if valid:
            by={r['case']:r for r in rows};aa=by[cfg['cases'][0]['name']]['overall'];bb=by[cfg['cases'][1]['name']]['overall']
            item.update(rps_ratio_B_over_A=bb['rps']/aa['rps'],p95_ratio_B_over_A=bb['p95_ms']/aa['p95_ms'],p99_ratio_B_over_A=bb['p99_ms']/aa['p99_ms'])
        summary['pairs'].append(item)
    summary['all_three_pairs_qualified']=len(summary['pairs'])==3 and all(r['qualified'] for r in summary['pairs'])
    write_json(root/'summary.json',summary)
except BaseException as e:
    failure=type(e).__name__+': '+str(e)
    write_json(root/'controller-error.json',{'error':failure,'attempts':attempts})
    event('controller_error',error=failure)
finally:
    host_stop.set()
    if 'hostthread' in locals(): hostthread.join(timeout=10)
    final_budget_errors=[]
    if load_created:
        with contextlib.suppress(Exception): docker('stop','--time','10',loadname)
        try:
            final_load=inspect(loadname,root/'load-final-inspect.json')
            assert_budget(final_load,protocol['load_cgroup_cpus'],4*1024**3)
        except Exception as e:
            final_budget_errors.append('final load budget verification failed: '+str(e))
    try:
        final_target=inspect(target,root/'target-final-inspect.json')
        assert_budget(final_target,8,16*1024**3)
    except Exception as e:
        final_budget_errors.append('final target budget verification failed: '+str(e))
    if final_budget_errors:failure=failure or '; '.join(final_budget_errors)
    write_json(root/'final-resource-check.json',{'valid':not final_budget_errors,'errors':final_budget_errors,
                                               'load_cgroup_cpus':protocol['load_cgroup_cpus'],'target_cgroup_cpus':8})
    if (root/'summary.json').exists():
        summary=json.loads((root/'summary.json').read_text())
        summary['final_resource_valid']=not final_budget_errors
        if final_budget_errors:summary['all_three_pairs_qualified']=False
        write_json(root/'summary.json',summary)
    event('controller_finished',output=str(root),error=failure)
    events.close()
raise SystemExit(1 if failure else 0)
