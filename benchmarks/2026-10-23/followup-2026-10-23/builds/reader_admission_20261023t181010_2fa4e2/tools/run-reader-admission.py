#!/usr/bin/env python3
"""Execute one authorized isolated correctness checkpoint; never a benchmark."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parent
TARGET='multicore-comparison-target-20261023'
EXPECTED='9016ff93e924c0d94652490ac895d1fbc64153fd9d3ea4b8b52b66ae892c3424'
stamp=time.strftime('%Y%m%dt%H%M%S',time.gmtime())+'_'+uuid.uuid4().hex[:6]
out=ROOT/'builds'/('reader_admission_'+stamp)
out.mkdir(exist_ok=False)
inside='/comparison/optimization/builds/'+out.name
db='mc_pair_reader_'+stamp
source=ROOT/'candidates/leader2'
case={'name':'leader2','binary':'/comparison/optimization/candidates/leader2/bin/conduit',
      'source_dir':'/comparison/optimization/candidates/leader2',
      'env':{'WORKERS':'1','PG_READERS':'1','PG_READ_GROUPS':'1','HASHERS':'1',
             'READ_BATCH':'32','READ_HOLD':'1','READ_BATCH_US':'5000','WRITE_BATCH_US':'1000',
             'ARTICLE_BATCH':'1','BCRYPT_BATCH_MS':'250'}}
result={'scope':'Isolated reader-admission correctness only; no capacity/performance claim',
        'created_unix_s':time.time(),'expected_binary_sha256':EXPECTED,'database':db,
        'pass':False,'runtime_started':False,'commands':[],'power':[]}

def write(path,value): path.write_text(json.dumps(value,indent=2)+'\n')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def power():
    p=subprocess.run(['pmset','-g','batt'],text=True,capture_output=True,timeout=5)
    text=p.stdout
    row={'unix_s':time.time(),'exit':p.returncode,'stdout':text,'stderr':p.stderr,
         'charging':p.returncode==0 and "'AC Power'" in text and ('; charging;' in text or '; charged;' in text)}
    result['power'].append(row);write(out/'result.json',result)
    return row['charging']
def command(argv,name,timeout=120,allowed=(0,)):
    p=subprocess.run(argv,text=True,capture_output=True,timeout=timeout)
    (out/name).write_text(p.stdout+p.stderr)
    result['commands'].append({'argv':argv,'exit':p.returncode,'log':name})
    if p.returncode not in allowed: raise RuntimeError(name+' exited '+str(p.returncode)+': '+p.stdout[-500:]+p.stderr[-1200:])
    return p
def dex(argv,name,**kw):return command(['docker','exec','--user','root',TARGET,*argv],name,**kw)
def ctl(action,name,*args):
    return dex(['python3',inside+'/tools/target_helper.py',action,'--out',inside+'/'+name,*args],action+'-'+name.replace('/','-')+'.log')
def inspect(name):
    p=command(['docker','inspect',TARGET],name+'.log')
    obj=json.loads(p.stdout)[0];write(out/(name+'.json'),obj)
    h=obj['HostConfig']
    assert h['NanoCpus']==8000000000 and h['Memory']==16*1024**3 and h['MemorySwap']==16*1024**3 and not h['CpusetCpus']
    return obj
def sources():
    skip={'.git','.goose','.goose-home','.build','.deps','bin','target','node_modules','__pycache__'}
    return {str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and not any(x in skip for x in p.relative_to(source).parts)}

tools=out/'tools';tools.mkdir()
shutil.copy2(Path(__file__),tools/'run-reader-admission.py')
shutil.copy2(ROOT/'tests/reader-admission.py',tools/'reader-admission.py')
shutil.copy2(ROOT/'tests/reader-admission-usage.md',tools/'reader-admission-usage.md')
shutil.copy2('/private/tmp/multicore-research-20261022/lab-target-control-v2.py',tools/'target_helper.py')
session='''import argparse,contextlib,json,os,pathlib,pwd,resource,subprocess,time,urllib.request
p=argparse.ArgumentParser();p.add_argument('role',choices=['proxy','app','probe']);p.add_argument('--root',required=True);a=p.parse_args()
root=pathlib.Path(a.root);cfg=json.loads((root/'session-config.json').read_text());role=a.role
user='challenge';uid=pwd.getpwnam(user).pw_uid;assert uid==501
env=os.environ.copy();env.update(cfg['environment'])
if role=='proxy':
 cmd=['python3',str(root/'tools/reader-admission.py'),'--proxy','--database-url',cfg['direct_database_url'],'--listen','127.0.0.1:15439','--wire-log',str(root/'wire.jsonl'),'--ready',str(root/'proxy-ready.json')]
 exe=os.path.realpath('/usr/bin/python3')
elif role=='app':
 cmd=[str(root/'frozen/app')];exe=os.path.realpath(cmd[0]);env['DATABASE_URL']=cfg['proxy_database_url']
else:
 cmd=['python3',str(root/'tools/reader-admission.py'),'--base',cfg['base'],'--database-url',cfg['direct_database_url'],'--secret',cfg['environment']['JWT_SECRET'],'--wire-log',str(root/'wire.jsonl'),'--out',str(root/'probe.json'),'--expected-readers','1','--expected-read-groups','1','--batch','32']
 exe=os.path.realpath('/usr/bin/python3')
wrapped=['runuser','-u',user,'--','prlimit','--nofile=200000:200000','--',*cmd]
with (root/(role+'.log')).open('x') as log:
 child=subprocess.Popen(wrapped,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
state={'launcher_pid':child.pid,'pgid':child.pid,'frozen_binary':exe,'app_user':user,'app_uid':uid,'role':role,'command':wrapped,'port':3039 if role=='app' else 15439,'start_monotonic_ns':time.monotonic_ns()}
text=pathlib.Path('/proc/'+str(child.pid)+'/stat').read_text();state['launcher_start_ticks']=int(text[text.rindex(')')+2:].split()[19]);(root/(role+'-state.json')).write_text(json.dumps(state,indent=2)+'\\n')
if role=='probe':
 code=child.wait();(root/'probe-exit.json').write_text(json.dumps({'exit':code})+'\\n');raise SystemExit(code)
for _ in range(60):
 if child.poll() is not None: raise RuntimeError(role+' exited early; inspect log')
 try:
  if role=='proxy':
   ready=json.loads((root/'proxy-ready.json').read_text());assert ready['ready'];break
  with urllib.request.urlopen(cfg['base']+'/api/tags',timeout=1) as r:
   if r.status==200:break
 except (OSError,ValueError,AssertionError):pass
 time.sleep(.25)
else:raise TimeoutError(role+' readiness timeout')
receipt=subprocess.run(['runuser','-u',user,'--','python3',str(root/'tools/target_helper.py'),'inspect-app','--case',str(root/(role+'-state.json')),'--out',str(root/(role+'-actual.json'))],text=True,capture_output=True,timeout=10)
assert receipt.returncode==0,receipt.stderr
actual=json.loads((root/(role+'-actual.json')).read_text());assert actual['valid'];print(json.dumps({'role':role,'ready':True,'actual_uid':uid,'nofile':200000}))
'''
(tools/'session.py').write_text(session)
write(out/'case.json',case)
environment={**case['env'],'JWT_SECRET':'multicore-server-challenge','HOST':'127.0.0.1','PORT':'3039',
             'PGHOST':'127.0.0.1','PGPORT':'5432','PGUSER':'postgres','PGPASSWORD':'challenge-test-only'}
write(out/'session-config.json',{'environment':environment,'base':'http://127.0.0.1:3039',
      'direct_database_url':'postgres://postgres:challenge-test-only@127.0.0.1:5432/'+db,
      'proxy_database_url':'postgres://conduit:conduit@127.0.0.1:15439/'+db})
write(out/'tool-sha256.json',{p.name:sha(p) for p in tools.iterdir() if p.is_file()})
before=sources();write(out/'source-before.json',before)
assert sha(source/'bin/conduit')==EXPECTED

try:
    assert power(),'requires effective AC charging before runtime'
    initial=inspect('target-before');result['target_was_running']=initial['State']['Running']
    command(['docker','start',TARGET],'target-start.log')
    result['runtime_started']=True
    ready=dex(['pg_isready'],'pg-isready.log',allowed=(0,1,2))
    if ready.returncode: dex(['pg_ctlcluster','18','main','start'],'pg-start.log')
    ctl('snapshot','target-initial.json')
    snap=json.loads((out/'target-initial.json').read_text());settings={s['name']:s['setting'] for s in snap['pg_settings']}
    assert settings['server_version_num'].startswith('18') and settings['max_connections']=='100'
    assert all(settings[k]=='on' for k in ['fsync','synchronous_commit','full_page_writes'])
    ctl('freeze','frozen','--case',inside+'/case.json')
    frozen=json.loads((out/'frozen/metadata.json').read_text())
    assert frozen['binary_sha256']==EXPECTED and frozen['source_sha256']==before
    ctl('clone','database.json','--database',db)
    for role in ['proxy','app']:
        assert power(),'power changed before '+role
        dex(['python3',inside+'/tools/session.py',role,'--root',inside],role+'-start.log')
    assert power(),'power changed before correctness probe'
    argv=['docker','exec','--user','root',TARGET,'python3',inside+'/tools/session.py','probe','--root',inside]
    with (out/'probe-driver.log').open('x') as log:
        proc=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+150
        while proc.poll() is None:
            if not power() or time.monotonic()>deadline:
                if (out/'probe-state.json').exists():ctl('stop','probe-stopped-early.json','--case',inside+'/probe-state.json')
                proc.wait(timeout=15)
                raise RuntimeError('probe stopped: power precondition or150s deadline')
            time.sleep(2)
    result['commands'].append({'argv':argv,'exit':proc.returncode,'log':'probe-driver.log'})
    assert proc.returncode==0,'probe failed; preserve probe.json/probe.log'
    measured=json.loads((out/'probe.json').read_text())
    assert measured['pass'] and measured['wire_observed'] and measured['fixture_cleaned']
    result['pass']=True
except BaseException as error:
    result['error']=type(error).__name__+': '+str(error)
finally:
    for role in ['probe','app','proxy']:
        if (out/(role+'-state.json')).exists():
            try:ctl('stop',role+'-stopped.json','--case',inside+'/'+role+'-state.json')
            except Exception as error:result['pass']=False;result[role+'_stop_error']=str(error)
    if (out/'database.json').exists():
        try:ctl('drop','dropped.json','--database',db)
        except Exception as error:result['pass']=False;result['drop_error']=str(error)
    if result['runtime_started']:
        with contextlib.suppress(Exception):ctl('snapshot','target-final.json')
    after=sources();write(out/'source-after.json',after)
    result['source_unchanged']=after==before
    result['binary_sha256_after']=sha(source/'bin/conduit')
    result['frozen_binary_sha256_after']=sha(out/'frozen/app') if (out/'frozen/app').exists() else None
    result['binary_unchanged']=result['binary_sha256_after']==EXPECTED and result['frozen_binary_sha256_after']==EXPECTED
    result['pass']=result['pass'] and result['source_unchanged'] and result['binary_unchanged']
    charging=power()
    if result['runtime_started'] and not charging:
        command(['docker','stop','--time','20',TARGET],'target-stop-low-power.log')
        result['target_left']='stopped: charging precondition absent'
    elif result['runtime_started']:result['target_left']='PG target idle; owned app/proxy stopped and clone dropped'
    with contextlib.suppress(Exception):inspect('target-after')
    result['finished_unix_s']=time.time();write(out/'result.json',result)
print(json.dumps({'output':str(out),'pass':result['pass'],'error':result.get('error'),'target_left':result.get('target_left')}),flush=True)
raise SystemExit(0 if result['pass'] else 1)
