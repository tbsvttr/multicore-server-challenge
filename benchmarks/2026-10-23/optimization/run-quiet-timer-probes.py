#!/usr/bin/env python3
"""Verify the enabled and disabled read timer using real HTTP, outside load trials."""
import datetime
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
out = root/'builds/quiet1'
out.mkdir(exist_ok=False)
croot = '/comparison/optimization/builds/quiet1'
target = 'multicore-comparison-target-20261023'
helper = '/evidence/lab-target-control-v2.py'
db = 'mc_pair_quiet_'+datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S')

def run(args, name, timeout=180):
    proc = subprocess.run(['docker','exec','--user','root',target,*args],text=True,capture_output=True,timeout=timeout)
    (out/name).write_text(proc.stdout+proc.stderr)
    if proc.returncode:
        raise RuntimeError(str(proc.returncode)+': '+proc.stdout[-1200:]+proc.stderr[-1600:])

def ctl(action, name, *args):
    run(['python3',helper,action,'--out',croot+'/'+name,*args],action+'-'+name.replace('/','-')+'.log')

error = None
try:
    ctl('clone','database.json','--database',db)
    for delay in [500000,0]:
        name = 'delay'+str(delay)
        (out/name).mkdir()
        case = {'name':name,'binary':'/comparison/optimization/candidates/windowtimer/bin/conduit',
                'source_dir':'/comparison/optimization/candidates/windowtimer',
                'env':{'WORKERS':'1','PG_READERS':'3','HASHERS':'1','ARTICLE_BATCH':'1',
                       'READ_BATCH_US':str(delay),'WRITE_BATCH_US':'1000'}}
        cf = croot+'/'+name+'/case.json'
        (out/name/'case.json').write_text(json.dumps(case,indent=2)+'\n')
        ctl('freeze',name+'/frozen','--case',cf)
        case['metadata'] = croot+'/'+name+'/frozen/metadata.json'
        (out/name/'case.json').write_text(json.dumps(case,indent=2)+'\n')
        try:
            ctl('start',name+'/app.json','--case',cf,'--database',db,'--port','3030')
            run(['env','BASE=http://127.0.0.1:3030','JWT_SECRET=multicore-server-challenge',
                 'DATABASE_URL=postgres://postgres:challenge-test-only@127.0.0.1:5432/'+db,
                 'python3','/comparison/optimization/tests/quiet-read-timer.py',
                 '--expected-us',str(delay),'--out',croot+'/'+name+'/probe.json'],name+'.log')
            result = json.loads((out/name/'probe.json').read_text())
            assert result['pass'],result
            print(json.dumps({'delay_us':delay,'pass':True}),flush=True)
        finally:
            if (out/name/'app.json').exists():
                ctl('stop',name+'/stopped.json','--case',croot+'/'+name+'/app.json')
except BaseException as exc:
    error = type(exc).__name__+': '+str(exc)
finally:
    if (out/'database.json').exists():
        try:
            ctl('drop','dropped.json','--database',db)
        except Exception as exc:
            error = (error or '')+' drop:'+str(exc)
    (out/'result.json').write_text(json.dumps({'pass':error is None,'error':error},indent=2)+'\n')
print(json.dumps({'output':str(out),'pass':error is None,'error':error}),flush=True)
raise SystemExit(1 if error else 0)
