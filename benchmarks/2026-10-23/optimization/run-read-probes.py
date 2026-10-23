#!/usr/bin/env python3
"""Compare contended candidate reads with stock singletons in an owned test DB."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--candidate', default='combined1')
p.add_argument('--output', default='read1')
p.add_argument('--read-batch-us', type=int, default=0)
a = p.parse_args()
assert a.candidate.replace('_','').isalnum() and a.output.replace('_','').isalnum()
assert 0 <= a.read_batch_us <= 1000000
root = Path(__file__).resolve().parent
out = root/'builds'/a.output
out.mkdir(exist_ok=False)
croot = '/comparison/optimization/builds/'+a.output
target = 'multicore-comparison-target-20261023'
helper = '/evidence/lab-target-control-v2.py'
db = 'mc_pair_reads_'+datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S')
cases = [
    {'name':'stock','binary':'/work/submissions/goose-native-tbsvttr/bin/conduit',
     'source_dir':'/work/submissions/goose-native-tbsvttr',
     'env':{'WORKERS':'1','PG_READERS':'3','HASHERS':'1','ARTICLE_BATCH':'0'}},
    {'name':a.candidate,'binary':'/comparison/optimization/candidates/'+a.candidate+'/bin/conduit',
     'source_dir':'/comparison/optimization/candidates/'+a.candidate,
     'env':{'WORKERS':'1','PG_READERS':'3','HASHERS':'1','ARTICLE_BATCH':'1','READ_BATCH':'32','READ_HOLD':'1',
            'READ_BATCH_US':str(a.read_batch_us)}},
]

def run(args, log, timeout=180):
    proc = subprocess.run(['docker','exec','--user','root',target,*args],
                          text=True,capture_output=True,timeout=timeout)
    (out/log).write_text(proc.stdout+proc.stderr)
    if proc.returncode:
        raise RuntimeError(str(proc.returncode)+': '+proc.stdout[-1000:]+proc.stderr[-2000:])
    return proc

def control(action, name, *args):
    return run(['python3',helper,action,'--out',croot+'/'+name,*args],
               action+'-'+name.replace('/','-')+'.log',timeout=240)

error = None
try:
    control('clone','database.json','--database',db)
    for index, case in enumerate(cases):
        sub = out/case['name']
        sub.mkdir()
        cf = croot+'/'+case['name']+'/case.json'
        (sub/'case.json').write_text(json.dumps(case,indent=2)+'\n')
        control('freeze',case['name']+'/frozen','--case',cf)
        case['metadata'] = croot+'/'+case['name']+'/frozen/metadata.json'
        (sub/'case.json').write_text(json.dumps(case,indent=2)+'\n')
        control('start',case['name']+'/app.json','--case',cf,'--database',db,'--port',str(3031+index))
    env = ['env','JWT_SECRET=multicore-server-challenge',
           'DATABASE_URL=postgres://postgres:challenge-test-only@127.0.0.1:5432/'+db]
    run([*env,'python3','/comparison/optimization/tests/read-batches.py',
         '--baseline','http://127.0.0.1:3031','--candidate','http://127.0.0.1:3032',
         '--out',croot+'/read-batches.json'],'read-batches.log',timeout=240)
    result = json.loads((out/'read-batches.json').read_text())
    assert result['pass'],result.get('failures')
    print(json.dumps({'read_batch_probes_pass':True,'requests':result['http_requests']}),flush=True)
except BaseException as exc:
    error = type(exc).__name__+': '+str(exc)
finally:
    for case in reversed(cases):
        if (out/case['name']/'app.json').exists():
            try:
                control('stop',case['name']+'/stopped.json','--case',croot+'/'+case['name']+'/app.json')
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
