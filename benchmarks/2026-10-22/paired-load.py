#!/usr/bin/env python3
"""Prepare or execute six retained ARM64/Docker local comparison attempts.

Default is a network-free dry plan. --execute requires an existing frozen plan.
"""
import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import subprocess
import threading
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--config')
p.add_argument('--plan',required=True)
p.add_argument('--execute',action='store_true')
p.add_argument('--smoke',action='store_true',help='prepare a separate1k-user correctness-only10/15/5s smoke plan')
p.add_argument('--smoke-case',type=int,choices=[0,1],default=1)
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
    users=1000 if a.smoke else cfg.get('users',10000)
    assert 1000<=users<=20000,'one-address initial protocol permits1k–20k users'
    for case in cfg['cases']:
        assert case['name'].replace('_','').isalnum() and len(case['name'])<=20
        assert case['binary'].startswith('/') and case['source_dir'].startswith('/')
    assert cfg['cases'][0]['name']!=cfg['cases'][1]['name']
    scope='local ARM64 Mac/Docker correctness-only modified-duration smoke' if a.smoke else 'local ARM64 Mac/Docker fixed-load comparison; not an official score or capacity search'
    order=[[a.smoke_case]] if a.smoke else [[0,1],[1,0],[0,1]]
    ramp,measure,tail=(10,15,5) if a.smoke else (60,60,15)
    plan={'scope':scope,
          'configuration':cfg,'configuration_sha256':sha(a.config),
          'protocol':{'smoke':a.smoke,'users':users,'articles':500000,'think_scale':1.0,'ramp_s':ramp,'measure_s':measure,'tail_s':tail,
                      'pairs':0 if a.smoke else 3,'order':order,'fresh_full_seed_per_attempt':True,
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
hostroot=pathlib.Path(cfg.get('host_evidence','/private/tmp/multicore-research-20261022')).resolve()
target=cfg.get('target_container','multicore-goose-dev-20261022')
stamp=time.strftime('%Y%m%dT%H%M%S',time.gmtime()).lower()
runname='pair_'+stamp+'_'+os.urandom(3).hex()
root=hostroot/'paired-load'/runname
root.mkdir(parents=True,exist_ok=False)
container_root='/evidence/paired-load/'+runname
loadname='multicore-load-'+runname.replace('_','-')
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
    return docker('exec','--user','root',target,'python3','/evidence/lab-target-control.py',action,'--out',out,*argv,**kw)

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
    docker('exec','--user','root','-d',container,'python3','/evidence/lab-monitor.py','--out',path+'.jsonl',
           '--stop',path+'.stop','--app-pgid',str(app_pgid))

def summarize_monitor(path,start_ms,end_ms,quota):
    rows=[json.loads(line) for line in pathlib.Path(path).read_text().splitlines()]
    selected=[r for r in rows if start_ms<=r['wall_ns']/10**6<=end_ms]
    if len(selected)<2: return {'valid_sampling':False,'samples':len(selected)}
    first,last=selected[0],selected[-1]
    elapsed=(last['monotonic_ns']-first['monotonic_ns'])/10**9
    cpu=(last['cpu']['usage_usec']-first['cpu']['usage_usec'])/10**6
    out={'samples':len(selected),'elapsed_s':elapsed,'cgroup_cpu_quota_pct':cpu/elapsed/quota*100,
         'memory_peak_sampled_bytes':max(int(r['memory.current']) for r in selected),
         'swap_peak_sampled_bytes':max(int(r['memory.swap.current']) for r in selected),
         'max_sample_gap_s':max((b['monotonic_ns']-x['monotonic_ns'])/10**9 for x,b in zip(selected,selected[1:])),
         'memory_events_before':first['memory.events'],'memory_events_after':last['memory.events']}
    out['valid_sampling']=out['max_sample_gap_s']<=3
    for kind in ['app','pg']:
        out[kind+'_whole_target_pct']=(last[kind]['cpu_s']-first[kind]['cpu_s'])/elapsed/8*100
        out[kind+'_rss_sum_peak_bytes']=max(r[kind]['rss_bytes'] for r in selected)
    return out

attempts=[]
failure=None
try:
    targetobj=inspect(target,root/'target-inspect.json')
    assert_budget(targetobj,8,16*1024**3)
    assert targetobj['State']['Running']
    control('snapshot',container_root+'/target-initial.json')
    initial=json.loads((root/'target-initial.json').read_text())
    low,high=map(int,initial['ip_local_port_range'].split())
    assert protocol['users']<high-low-1024,'not enough ports for one-address protocol'
    # Refuse an occupied port instead of stopping somebody else's server.
    check="import socket,sys;s=socket.socket();s.settimeout(.3);sys.exit(1 if s.connect_ex(('127.0.0.1',int(sys.argv[1])))==0 else 0)"
    docker('exec','--user','root',target,'python3','-c',check,str(cfg.get('port',3000)))
    image=cfg.get('load_image') or targetobj['Image']
    docker('run','-d','--user','root','--name',loadname,'--label','multicore.local.owner='+runname,
           '--cpus','2','--memory','4g','--memory-swap','4g','--ulimit','nofile=200000:200000',
           '--network','container:'+target,'--volume',str(hostroot)+':/evidence:rw',
           '--entrypoint','/bin/sh',image,'-c','exec sleep infinity')
    load_created=True
    loadobj=inspect(loadname,root/'load-inspect.json')
    assert_budget(loadobj,2,4*1024**3)
    write_json(root/'tool-source-sha256.json',{str(f.relative_to(hostroot)):sha(f) for f in
        [hostroot/'tools/loadgen',hostroot/'lab-monitor.py',hostroot/'lab-target-control.py',hostroot/'paired-load.py']})
    (root/'frozen').mkdir()
    for case in cfg['cases']:
        casepath=root/(case['name']+'.json')
        write_json(casepath,case)
        control('freeze',container_root+'/frozen/'+case['name'],'--case',container_root+'/'+case['name']+'.json')
        case['metadata']=container_root+'/frozen/'+case['name']+'/metadata.json'
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
            proc=None
            try:
                control('clone',cdir+'/database.json','--database',db,timeout=180)
                control('snapshot',cdir+'/before.json')
                control('start',cdir+'/app.json','--database',db,'--case',container_root+'/'+case['name']+'.json',
                        '--port',str(cfg.get('port',3000)),'--secret',cfg.get('jwt_secret','multicore-server-challenge'),timeout=75)
                app=json.loads((attempt/'app.json').read_text())
                start_monitor(target,cdir+'/target-monitor',app['pgid'])
                start_monitor(loadname,cdir+'/load-monitor')
                start_ms=int(time.time()*1000)+5000
                argv=['docker','exec','--user','root','--env','GOMAXPROCS=2',loadname,'/evidence/tools/loadgen','run',
                      '-target','http://127.0.0.1:'+str(cfg.get('port',3000)),'-users',str(protocol['users']),
                      '-ramp',str(protocol['ramp_s'])+'s','-measure',str(protocol['measure_s'])+'s','-tail',str(protocol['tail_s'])+'s','-articles','500000','-think-scale','1',
                      '-box-index','0','-id-offset','0','-start-at',str(start_ms),'-run-id',runname+'-pair'+str(pair),
                      '-secret',cfg.get('jwt_secret','multicore-server-challenge'),'-out',cdir+'/box0.json']
                write_json(attempt/'load-command.json',argv)
                with (attempt/'load.log').open('x') as log:
                    proc=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT)
                    max_seconds=protocol['ramp_s']+protocol['measure_s']+protocol['tail_s']+40
                    deadline=time.monotonic()+max_seconds
                    heartbeat=time.monotonic()+15
                    while proc.poll() is None:
                        if time.monotonic()>deadline:
                            proc.terminate()
                            kill="import pathlib,os,signal;[(os.kill(int(p.parent.name),signal.SIGTERM)) for p in pathlib.Path('/proc').glob('[0-9]*/exe') if p.exists() and os.path.realpath(p)=='/evidence/tools/loadgen']"
                            docker('exec','--user','root',loadname,'python3','-c',kill)
                            raise TimeoutError('native load client exceeded declared duration+40s; owned generator terminated')
                        if time.monotonic()>=heartbeat:
                            event('attempt_running',id=name);heartbeat+=15
                        time.sleep(1)
                    state['load_exit']=proc.returncode
                if proc.returncode: raise RuntimeError('native load client failed; see load.log')
                merged=docker('exec','--user','root',loadname,'/evidence/tools/loadgen','merge','-o',cdir+'/merged.json',cdir+'/box0.json',
                              allowed=(0,3),save=attempt/'merged.txt')
                state['merge_exit']=merged.returncode
                result=json.loads((attempt/'merged.json').read_text())
                state.update(verdict=result['verdict'],overall=result['overall'],boxes=result['boxes'])
                state['classification']='INVALID_GENERATOR' if result['verdict']['lg_limited'] else 'PASS' if result['verdict']['pass'] else 'FAIL_SLO'
            except Exception as e:
                state['classification']='INVALID_INFRASTRUCTURE';state['error']=type(e).__name__+': '+str(e)
            finally:
                for who in ['target','load']:(attempt/(who+'-monitor.stop')).touch()
                time.sleep(1.2)
                try:
                    if (attempt/'box0.json').exists():
                        raw=json.loads((attempt/'box0.json').read_text());meta=raw['meta']
                        for who,quota in [('target',8),('load',2)]:
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
                except Exception as e: state['after_snapshot_error']=str(e)
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
    if protocol.get('smoke'):
        summary['smoke_only']=True
        summary['smoke_pass']=len(attempts)==1 and attempts[0]['classification']=='PASS'
    else:
        summary['all_three_pairs_qualified']=len(summary['pairs'])==3 and all(r['qualified'] for r in summary['pairs'])
    write_json(root/'summary.json',summary)
except BaseException as e:
    failure=type(e).__name__+': '+str(e)
    write_json(root/'controller-error.json',{'error':failure,'attempts':attempts})
    event('controller_error',error=failure)
finally:
    host_stop.set()
    if 'hostthread' in locals(): hostthread.join(timeout=10)
    if load_created:
        with contextlib.suppress(Exception): docker('stop','--time','10',loadname)
        with contextlib.suppress(Exception): inspect(loadname,root/'load-final-inspect.json')
    with contextlib.suppress(Exception): inspect(target,root/'target-final-inspect.json')
    event('controller_finished',output=str(root),error=failure)
    events.close()
raise SystemExit(1 if failure else 0)
