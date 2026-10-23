#!/usr/bin/env python3
"""Run correctness probes on a private, disposable full-seed database."""
import datetime
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
out = root / 'builds/runtime_leader2'
out.mkdir(exist_ok=False)
croot = '/comparison/optimization/builds/runtime_leader2'
target = 'multicore-comparison-target-20261023'
helper = '/evidence/lab-target-control-v2.py'
db = 'mc_pair_runtime_' + datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S')
case = {'name':'leader2','binary':'/comparison/optimization/candidates/leader2/bin/conduit',
        'source_dir':'/comparison/optimization/candidates/leader2',
        'env':{'WORKERS':'1','PG_READERS':'3','HASHERS':'1','BCRYPT_BATCH_MS':'10',
               'WRITE_BATCH_US':'50000','ARTICLE_BATCH':'1'}}
(out / 'case.json').write_text(json.dumps(case,indent=2)+'\n')

def run(args, log, timeout=180):
    proc = subprocess.run(['docker','exec','--user','root',target,*args],
                          text=True,capture_output=True,timeout=timeout)
    (out / log).write_text(proc.stdout+proc.stderr)
    if proc.returncode:
        raise RuntimeError(str(proc.returncode)+': '+proc.stdout[-1000:]+proc.stderr[-2000:])
    return proc

def control(action, name, *args):
    return run(['python3',helper,action,'--out',croot+'/'+name,*args],action+'-'+name.replace('/','-')+'.log')

error = None
try:
    control('freeze','frozen','--case',croot+'/case.json')
    case['metadata'] = croot+'/frozen/metadata.json'
    (out/'case.json').write_text(json.dumps(case,indent=2)+'\n')
    control('clone','database.json','--database',db)
    control('start','app.json','--case',croot+'/case.json','--database',db,'--port','3030')
    env = ['env','BASE=http://127.0.0.1:3030','JWT_SECRET=multicore-server-challenge',
           'DATABASE_URL=postgres://conduit:conduit@127.0.0.1:5432/'+db,
           'PGHOST=127.0.0.1','PGUSER=postgres','PGPASSWORD=challenge-test-only']
    for name, script in [('runtime-write','/comparison/optimization/tests/runtime-write-probe-v2.py'),
                         ('favorite-race','/evidence/favorite-race-probe.py')]:
        run([*env,'python3',script,'--out',croot+'/'+name+'.json'],name+'.log')
        result = json.loads((out/(name+'.json')).read_text())
        assert result['pass'],name
        print(json.dumps({'probe':name,'pass':True}),flush=True)
except BaseException as exc:
    error = type(exc).__name__+': '+str(exc)
finally:
    if (out/'app.json').exists():
        try:
            control('stop','stopped.json','--case',croot+'/app.json')
        except Exception as exc:
            error = (error or '')+' stop:'+str(exc)
    if (out/'database.json').exists():
        try:
            control('drop','dropped.json','--database',db)
        except Exception as exc:
            error = (error or '')+' drop:'+str(exc)
    (out/'result.json').write_text(json.dumps({'error':error,'pass':error is None},indent=2)+'\n')
print(json.dumps({'output':str(out),'pass':error is None,'error':error}),flush=True)
raise SystemExit(1 if error else 0)
