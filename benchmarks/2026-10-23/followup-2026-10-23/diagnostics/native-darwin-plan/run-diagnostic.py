#!/usr/bin/env python3
"""One unchanged-workload native-Darwin 10k diagnostic; never a capacity score.

Requires an explicitly prepared loopback target and effective charging. Root
executes only after review, preferably inside diagnostics/run-with-power-guard.py.
No target creation, builds, host tuning or workload-source edits occur here.
"""
import argparse
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import threading
import time
import uuid

PLAN=Path(__file__).resolve().parent
OPT=PLAN.parents[1]
HOST_MOUNT=OPT.parent.resolve()
EXPECTED_CLIENT='c6053653c26c2136bd7bd007df68cfb8cf51975f9bf8e6f38bcebdd7484076e9'
EXPECTED_APP='7a7c31fbaedbb9687f048158623b3c311ea5f240ecc4bfcff985b718bd2afc21'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def inside(path):return '/comparison/'+str(path.resolve().relative_to(HOST_MOUNT))
def source_hashes(root,skip=()):
    return {str(f.relative_to(root)):sha(f) for f in root.rglob('*') if f.is_file() and not any(p in skip for p in f.relative_to(root).parts)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-preparation',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    a=parser.parse_args()
    if not a.execute:parser.error('preparation is static; --execute requires root scheduling and stable charging')
    def interrupted(signum,frame):raise KeyboardInterrupt('signal '+str(signum))
    for sig in [signal.SIGTERM,signal.SIGHUP]:signal.signal(sig,interrupted)
    if os.getuid()!=501 or os.geteuid()!=501:raise RuntimeError('run the native driver/client as normal UID501')
    out=a.out.resolve();out.relative_to(HOST_MOUNT);out.mkdir(parents=True,exist_ok=False)
    croot=inside(out)
    run_id='native10k_'+time.strftime('%Y%m%dt%H%M%S',time.gmtime())+'_'+uuid.uuid4().hex[:6]
    database='mc_pair_'+run_id
    prep=json.loads((a.target_preparation/'proof.json').read_text())
    assert prep['old_preserved_stopped'] and prep['server_cpus']==8 and prep['server_memory_bytes']==16*1024**3
    assert prep['no_swap'] and prep['no_affinity'] and prep['original_pg_settings_equal'] and prep['original_sources_equal']
    assert prep['loopback_ports']==list(range(33000,33016))
    target=prep['new_target']
    result={'scope':'DIAGNOSTIC ONLY: native Darwin client outside Docker VM; no controlled causal comparison',
            'run_id':run_id,'database':database,'target':target,'completed':False,'capacity_score':False,
            'client_headroom_qualified':False,'hard_client_CPU_memory_quota':None,
            'native_box_CPU':'N/A on Darwin; native75% headroom is not proven',
            'commands':[],'started_unix_s':time.time(),'power':[],'cleanup_errors':[]}
    tools=out/'tools';tools.mkdir()
    for source,name in [(Path(__file__),'run-diagnostic.py'),
                        (OPT/'diagnostics/run-with-power-guard.py','run-with-power-guard.py'),
                        (Path('/private/tmp/multicore-research-20261022/lab-target-control-v2.py'),'target_helper.py'),
                        (Path('/private/tmp/multicore-research-20261022/lab-monitor.py'),'target_monitor.py')]:
        shutil.copy2(source,tools/name)
    shutil.copy2(a.target_preparation/'proof.json',out/'target-preparation-proof.json')
    client_root=out/'client-frozen';client_root.mkdir()
    shutil.copy2(PLAN/'loadgen-darwin',client_root/'loadgen-darwin')
    assert sha(client_root/'loadgen-darwin')==EXPECTED_CLIENT
    app_source=OPT/'candidates/leader1'
    skip={'.git','.goose','.goose-home','.build','.deps','bin','target','node_modules','__pycache__'}
    before=source_hashes(app_source,skip);write(out/'app-source-before.json',before)
    bench=Path('/private/tmp/multicore-challenge-20261022/bench')
    native_source={str(f.relative_to(bench)):sha(f) for f in bench.rglob('*') if f.is_file() and (f.suffix=='.go' or f.name in ['go.mod','go.sum'])}
    write(out/'native-source-before.json',native_source)
    assert sha(app_source/'bin/conduit')==EXPECTED_APP
    case={'name':'goose32-sourceA','binary':'/comparison/optimization/candidates/leader1/bin/conduit',
          'source_dir':'/comparison/optimization/candidates/leader1','source_revision':'23a14e8cbf32113509cd0ad941320ef947508981',
          'expected_binary_sha256':EXPECTED_APP,
          'env':{'WORKERS':'2','PG_READERS':'3','HASHERS':'2','BCRYPT_BATCH_MS':'250',
                 'READ_BATCH':'32','READ_HOLD':'1','ARTICLE_BATCH':'1','WRITE_BATCH_US':'1000','READ_BATCH_US':'5000'}}
    old_config=json.loads((OPT/'profiles/capacity-v3-powered-config.json').read_text())
    case['conformance']=next(c['conformance'] for c in old_config['cases'] if c['expected_binary_sha256']==EXPECTED_APP)
    conformance_log=Path(case['conformance']['log_host_path'])
    assert sha(conformance_log)==case['conformance']['log_sha256'] and '197 steps, 197 passed, 0 failed' in conformance_log.read_text()
    write(out/'case.json',case)
    write(out/'configuration.json',{'stage':'warmup-diagnostic','users':10000,'ramp_s':60,'measure_s':120,'tail_s':15,
          'articles':500000,'think_scale':1,'box_index':0,'id_offset':0,'start_delay_ms':5000,
          'client_env':{'GOMAXPROCS':'2','GODEBUG':'gctrace=1'},'normal_uid':501,'client_soft_nofile':32768,'client_hard_nofile':32768,
          'server_cpus':8,'server_memory_bytes':16*1024**3,'client_hard_CPU_memory_cap':None,
          'destinations':['http://127.0.0.1:'+str(p) for p in prep['loopback_ports']],
          'capacity_search_disabled':True,'holds_disabled':True,'prior_phase_reuse':False})

    def save():write(out/'result.json',result)
    def command(argv,name,timeout=120,allowed=(0,)):
        p=subprocess.run(argv,text=True,capture_output=True,timeout=timeout)
        (out/name).write_text(p.stdout+p.stderr)
        result['commands'].append({'argv':argv,'exit':p.returncode,'log':name});save()
        if p.returncode not in allowed:raise RuntimeError(name+' exited '+str(p.returncode)+': '+p.stderr[-1000:])
        return p
    def dex(argv,name,**kw):return command(['docker','exec','--user','root',target,*argv],name,**kw)
    def control(action,name,*args):return dex(['python3',croot+'/tools/target_helper.py',action,'--out',croot+'/'+name,*args],action+'-'+name.replace('/','-')+'.log')
    def power():
        p=subprocess.run(['pmset','-g','batt'],text=True,capture_output=True,timeout=5)
        safe=p.returncode==0 and "'AC Power'" in p.stdout and ('; charging;' in p.stdout or '; charged;' in p.stdout)
        result['power'].append({'unix_s':time.time(),'safe':safe,'stdout':p.stdout,'stderr':p.stderr,'exit':p.returncode});save()
        return safe
    def budget(obj):
        h=obj['HostConfig']
        assert h['NanoCpus']==8*10**9 and h['Memory']==16*1024**3 and h['MemorySwap']==16*1024**3 and not h['CpusetCpus']
        mappings=h['PortBindings']['3000/tcp']
        assert {(m['HostIp'],int(m['HostPort'])) for m in mappings}=={('127.0.0.1',n) for n in range(33000,33016)}
    client=None;client_log=None;monitor_thread=None;monitor_stop=threading.Event();backend_pids=[]
    clone_requested=False;target_monitor_requested=False

    client_launcher='''import hashlib,json,os,pathlib,resource,sys
root=pathlib.Path(sys.argv[1]);cfg=json.loads((root/'client-command.json').read_text());soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE)
assert os.getuid()==501 and os.geteuid()==501
assert hard==resource.RLIM_INFINITY or hard>=32768
resource.setrlimit(resource.RLIMIT_NOFILE,(32768,32768));env=os.environ.copy();env.update({'GOMAXPROCS':'2','GODEBUG':'gctrace=1'})
binary=cfg['argv'][0];assert hashlib.sha256(pathlib.Path(binary).read_bytes()).hexdigest()==cfg['expected_sha256']
witness={'pid':os.getpid(),'pgid':os.getpgrp(),'uid':os.getuid(),'euid':os.geteuid(),'nofile':resource.getrlimit(resource.RLIMIT_NOFILE),'env':{k:env[k] for k in ['GOMAXPROCS','GODEBUG']},'binary_sha256':cfg['expected_sha256'],'limit_witness':'actual same PID immediately before exec; exec preserves RLIMIT_NOFILE; fixed child hard limit also prevents runtime raising above32768'}
(root/'client-actual.json').write_text(json.dumps(witness,indent=2)+'\\n');os.execve(binary,cfg['argv'],env)
'''
    (tools/'client-launch.py').write_text(client_launcher)
    monitor_launcher='''import json,pathlib,subprocess,sys,time
root=pathlib.Path(sys.argv[1]);app=json.loads((root/'app.json').read_text())
with (root/'target-monitor.log').open('x') as log:
 p=subprocess.Popen(['python3',str(root/'tools/target_monitor.py'),'--out',str(root/'target-monitor.jsonl'),'--stop',str(root/'target-monitor.stop'),'--app-pgid',str(app['pgid'])],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
text=pathlib.Path('/proc/'+str(p.pid)+'/stat').read_text();state={'launcher_pid':p.pid,'pgid':p.pid,'launcher_start_ticks':int(text[text.rindex(')')+2:].split()[19])};(root/'monitor-state.json').write_text(json.dumps(state)+'\\n')
code=p.wait();(root/'monitor-exit.json').write_text(json.dumps({'exit':code})+'\\n')
'''
    (tools/'monitor-launch.py').write_text(monitor_launcher)
    write(out/'tool-sha256.json',{p.name:sha(p) for p in tools.iterdir() if p.is_file()})

    def host_monitor():
        errors=[];tick=0
        with (out/'darwin-monitor.jsonl').open('x') as stream:
            while not monitor_stop.is_set():
                start=time.monotonic();row={'wall_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns()}
                pidlist=','.join(str(p) for p in [client.pid,*backend_pids])
                for name,argv in [('processes',['ps','-ww','-p',pidlist,'-o','pid=,uid=,time=,%cpu=,rss=,comm=']),
                                  ('kernel_num_files',['sysctl','-n','kern.num_files'])]:
                    try:
                        p=subprocess.run(argv,text=True,capture_output=True,timeout=2)
                        row[name]={'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
                        if p.returncode:errors.append(name+': exit '+str(p.returncode))
                    except Exception as error:row[name]={'error':repr(error)};errors.append(name+': '+repr(error))
                if tick%10==0:
                    try:
                        p=subprocess.run(['vm_stat'],text=True,capture_output=True,timeout=2)
                        row['vm_stat']={'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
                        if p.returncode:errors.append('vm_stat: exit '+str(p.returncode))
                    except Exception as error:row['vm_stat']={'error':repr(error)};errors.append('vm_stat: '+repr(error))
                stream.write(json.dumps(row)+'\n');stream.flush();tick+=1
                monitor_stop.wait(max(.05,1-(time.monotonic()-start)))
        write(out/'darwin-monitor-exit.json',{'samples':tick,'complete':not errors,'errors':errors})

    save()
    try:
        assert power(),'effective stable AC charging required before any Docker action'
        inspected=json.loads(command(['docker','inspect',target],'target-before-inspect.log').stdout)[0]
        budget(inspected);write(out/'target-before-inspect.json',inspected)
        assert inspected['State']['Running'],'prepare/start the owned target before executing this driver'
        original=json.loads(command(['docker','inspect',prep['old_target']],'original-target-inspect.log').stdout)[0]
        assert not original['State']['Running'],'original checkpoint target must remain stopped'
        control('snapshot','target-initial.json')
        initial=json.loads((out/'target-initial.json').read_text());pg={r['name']:r['setting'] for r in initial['pg_settings']}
        assert pg['server_version_num'].startswith('18') and pg['max_connections']=='100' and all(pg[k]=='on' for k in ['fsync','synchronous_commit','full_page_writes'])
        control('freeze','server-frozen','--case',croot+'/case.json')
        meta=json.loads((out/'server-frozen/metadata.json').read_text());assert meta['binary_sha256']==EXPECTED_APP and meta['source_sha256']==before
        case['metadata']=croot+'/server-frozen/metadata.json';write(out/'case.json',case)
        clone_requested=True
        control('clone','database.json','--database',database)
        control('start','app.json','--case',croot+'/case.json','--database',database,'--port','3000')
        control('snapshot','before-load.json','--case',croot+'/app.json')
        assert power(),'charging lost before native workload'
        build_info=command(['go','version','-m',str(client_root/'loadgen-darwin')],'darwin-build-info.log')
        assert 'go1.27.2' in build_info.stdout,'unexpected Darwin build toolchain'
        limits=command(['sysctl','kern.maxfiles','kern.maxfilesperproc','kern.num_files'],'darwin-file-limits.log').stdout
        command(['sh','-c','ulimit -Sn; ulimit -Hn'],'driver-nofile.log')
        processes=command(['ps','-axo','pid=,comm='],'backend-pids.log').stdout
        backend_pids=[int(line.split(None,1)[0]) for line in processes.splitlines() if line.strip() and line.split(None,1)[-1].endswith('/com.docker.backend')]
        assert backend_pids,'Docker Desktop forwarding backend PID missing'
        target_monitor_requested=True
        command(['docker','exec','--user','root','-d',target,'python3',croot+'/tools/monitor-launch.py',croot],'monitor-start.log')
        deadline=time.monotonic()+10
        while True:
            if (out/'monitor-exit.json').exists():raise RuntimeError('target observer exited before workload')
            if (out/'monitor-state.json').exists() and (out/'target-monitor.jsonl').exists():
                line=(out/'target-monitor.jsonl').open().readline()
                if line.endswith('\n'):
                    first=json.loads(line)
                    assert first['wall_ns']>0 and first['monotonic_ns']>0 and first['cpu.max']
                    break
            if time.monotonic()>deadline:raise TimeoutError('target monitor state/first complete row missing')
            time.sleep(.05)
        alive="import json,pathlib,sys;s=json.loads(pathlib.Path(sys.argv[1]).read_text());t=pathlib.Path('/proc/'+str(s['launcher_pid'])+'/stat').read_text();p=t[t.rindex(')')+2:].split();assert p[0]!='Z' and int(p[19])==s['launcher_start_ticks'];print(json.dumps({'running':True,'pid':s['launcher_pid']}))"
        witness=dex(['python3','-c',alive,croot+'/monitor-state.json'],'monitor-running.log')
        write(out/'monitor-ready.json',{'actual_process':json.loads(witness.stdout),'first_row_sha256':hashlib.sha256(line.encode()).hexdigest(),'ready_before_start_at_selection':True})
        start_at=time.time_ns()//1000000+5000
        argv=[str(client_root/'loadgen-darwin'),'run','-target',','.join('http://127.0.0.1:'+str(n) for n in prep['loopback_ports']),
              '-users','10000','-box-index','0','-id-offset','0','-ramp','60s','-measure','120s','-tail','15s',
              '-articles','500000','-think-scale','1','-start-at',str(start_at),'-run-id',run_id,
              '-secret','multicore-server-challenge','-out',str(out/'box0.json')]
        write(out/'client-command.json',{'argv':argv,'expected_sha256':EXPECTED_CLIENT})
        client_log=(out/'client.log').open('x')
        client=subprocess.Popen([os.sys.executable,str(tools/'client-launch.py'),str(out)],stdout=client_log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+3
        while not (out/'client-actual.json').exists():
            if client.poll() is not None:raise RuntimeError('native client exited before actual launch witness')
            if time.monotonic()>deadline:raise TimeoutError('native actual launch witness missing')
            time.sleep(.02)
        witness=json.loads((out/'client-actual.json').read_text())
        assert witness['pid']==client.pid and witness['uid']==witness['euid']==501 and witness['nofile']==[32768,32768]
        assert witness['env']=={'GOMAXPROCS':'2','GODEBUG':'gctrace=1'}
        deadline=time.monotonic()+2
        libproc=ctypes.CDLL('/usr/lib/libproc.dylib')
        libproc.proc_pidpath.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_uint32]
        libproc.proc_pidpath.restype=ctypes.c_int
        while True:
            ps=command(['ps','-ww','-p',str(client.pid),'-o','pid=,uid=,pgid=,comm='],'client-exec-witness.log')
            native_path=ctypes.create_string_buffer(4096)
            n=libproc.proc_pidpath(client.pid,native_path,len(native_path))
            observed=os.fsdecode(native_path.value) if n>0 else None
            if observed and Path(observed).resolve()==(client_root/'loadgen-darwin').resolve():
                write(out/'client-exec-witness.json',{'pid':client.pid,'uid':501,'actual_executable':observed,
                       'proc_pidpath_bytes':n,'ps_output':ps.stdout,'inherited_soft_hard_nofile':[32768,32768]})
                break
            if time.monotonic()>deadline:raise TimeoutError('same-PID native exec not witnessed')
            time.sleep(.02)
        monitor_thread=threading.Thread(target=host_monitor,daemon=True);monitor_thread.start()
        end=time.monotonic()+240;next_power=time.monotonic()+5
        while client.poll() is None:
            if monitor_thread is not None and not monitor_thread.is_alive():raise RuntimeError('Darwin observer exited during workload')
            if time.monotonic()>end:raise TimeoutError('native diagnostic exceeded bounded phase deadline')
            if time.monotonic()>=next_power:
                assert power(),'charging lost during native diagnostic'
                next_power=time.monotonic()+5
            time.sleep(.5)
        result['client_exit']=client.returncode;assert client.returncode==0,'native run failed; raw log preserved'
        merged=command([str(client_root/'loadgen-darwin'),'merge','-o',str(out/'merged.json'),str(out/'box0.json')],'merged.log',allowed=(0,3))
        result['merge_exit']=merged.returncode
        raw=json.loads((out/'box0.json').read_text());merge=json.loads((out/'merged.json').read_text());m=raw['meta']
        assert m['users']==10000 and m['box_index']==m['id_offset']==0 and m['gomaxprocs']==2 and m['articles']==500000 and m['think_scale']==1
        assert m['ramp_s']==60 and m['measure_s']==120 and m['tail_s']==15 and m['run_id']==run_id and m['start_at_ms']==start_at
        assert m['window_start_ms']==start_at+60000 and m['window_end_ms']==start_at+180000
        assert raw['box']['cpu_avg_measure_pct'] is None and raw['box']['cpu_max_measure_pct'] is None and all(row['cpu_pct'] is None for row in raw['timeline'])
        result.update(native_verdict=merge['verdict'],native_box_CPU_missing=True,native_metadata_exact=True,
                      native_timing_and_error_flags_preserved=True,completed=True)
    except BaseException as error:
        result['error']=type(error).__name__+': '+str(error)
    finally:
        if client is not None and client.poll() is None:
            with contextlib.suppress(ProcessLookupError):os.killpg(client.pid,signal.SIGTERM)
            try:client.wait(timeout=3)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):os.killpg(client.pid,signal.SIGKILL)
                client.wait(timeout=3)
        if client_log:client_log.close()
        monitor_stop.set()
        if monitor_thread:monitor_thread.join(timeout=8)
        if target_monitor_requested:
            (out/'target-monitor.stop').write_text('stop\n')
            end=time.monotonic()+5
            while not (out/'monitor-exit.json').exists() and time.monotonic()<end:time.sleep(.1)
            if not (out/'monitor-exit.json').exists() and (out/'monitor-state.json').exists():
                try:control('stop','monitor-stopped.json','--case',croot+'/monitor-state.json')
                except Exception as error:result['cleanup_errors'].append('monitor: '+str(error))
        if (out/'app.json').exists():
            with contextlib.suppress(Exception):control('snapshot','after-load.json','--case',croot+'/app.json')
            try:control('stop','app-stopped.json','--case',croot+'/app.json')
            except Exception as error:result['cleanup_errors'].append('app: '+str(error))
        if clone_requested:
            try:control('drop','dropped.json','--database',database)
            except Exception as error:
                if 'database "'+database+'" does not exist' in str(error):
                    try:
                        absent=dex(['runuser','-u','postgres','--','psql','-XAt','-d','postgres','-c',"SELECT count(*) FROM pg_database WHERE datname='"+database+"'"],'drop-absence-check.log')
                        assert absent.stdout.strip()=='0'
                        write(out/'drop-absent.json',{'database':database,'absent':True,'create_receipt_missing':not (out/'database.json').exists()})
                    except Exception as checked:result['cleanup_errors'].append('clone: '+str(checked))
                else:result['cleanup_errors'].append('clone: '+str(error))
        result['app_source_unchanged']=source_hashes(app_source,skip)==before
        result['native_source_unchanged']={str(f.relative_to(bench)):sha(f) for f in bench.rglob('*') if f.is_file() and (f.suffix=='.go' or f.name in ['go.mod','go.sum'])}==native_source
        result['client_binary_unchanged']=sha(client_root/'loadgen-darwin')==sha(PLAN/'loadgen-darwin')==EXPECTED_CLIENT
        result['app_binary_unchanged']=sha(app_source/'bin/conduit')==EXPECTED_APP
        result['frozen_app_binary_unchanged']=sha(out/'server-frozen/app')==EXPECTED_APP if (out/'server-frozen/app').exists() else False
        target_exit=json.loads((out/'monitor-exit.json').read_text()) if (out/'monitor-exit.json').exists() else None
        host_exit=json.loads((out/'darwin-monitor-exit.json').read_text()) if (out/'darwin-monitor-exit.json').exists() else None
        result['target_observer_complete']=target_exit is not None and target_exit.get('exit')==0 and (out/'monitor-ready.json').exists()
        result['darwin_observer_complete']=host_exit is not None and host_exit.get('complete') is True
        result['completed']=result['completed'] and all(result[k] for k in ['app_source_unchanged','native_source_unchanged','client_binary_unchanged','app_binary_unchanged','frozen_app_binary_unchanged','target_observer_complete','darwin_observer_complete']) and not result['cleanup_errors']
        charging=power()
        if not charging and (out/'target-before-inspect.json').exists():
            try:command(['docker','stop','--time','20',target],'target-stop-low-power.log')
            except Exception as error:result['cleanup_errors'].append('target: '+str(error))
        result['finished_unix_s']=time.time();save()
    print(json.dumps({'output':str(out),'completed':result['completed'],'capacity_score':False,
                      'client_headroom_qualified':False,'error':result.get('error'),'cleanup_errors':result['cleanup_errors']}),flush=True)
    return 0 if result['completed'] and not result['cleanup_errors'] else 1


if __name__=='__main__':raise SystemExit(main())
