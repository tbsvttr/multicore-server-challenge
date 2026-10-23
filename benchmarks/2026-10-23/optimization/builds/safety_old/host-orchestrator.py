#!/usr/bin/env python3
"""Reproduce old edge cases or validate their fixes on an owned disposable DB."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser()
p.add_argument('--candidate',default='leader1')
p.add_argument('--baseline',action='store_true')
p.add_argument('--output',required=True)
a=p.parse_args()
assert a.candidate.replace('_','').isalnum() and a.output.replace('_','').isalnum()
root=Path(__file__).resolve().parent
out=root/'builds'/a.output
out.mkdir(exist_ok=False)
croot='/comparison/optimization/builds/'+a.output
target='multicore-comparison-target-20261023'
helper='/evidence/lab-target-control-v2.py'
db='mc_pair_safety_'+datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S')
source='/work/submissions/goose-native-tbsvttr' if a.baseline else '/comparison/optimization/candidates/'+a.candidate
case={'name':'stock' if a.baseline else a.candidate,'binary':source+'/bin/conduit','source_dir':source,
      'env':{'WORKERS':'1','PG_READERS':'3','HASHERS':'1','ARTICLE_BATCH':'1',
             'READ_BATCH_US':'5000','WRITE_BATCH_US':'1000'}}
(out/'case.json').write_text(json.dumps(case,indent=2)+'\n')

def run(args,name,timeout=240):
    proc=subprocess.run(['docker','exec','--user','root','--workdir','/work/bench',target,*args],
                        text=True,capture_output=True,timeout=timeout)
    (out/name).write_text(proc.stdout+proc.stderr)
    if proc.returncode:
        raise RuntimeError(str(proc.returncode)+': '+proc.stdout[-1200:]+proc.stderr[-1800:])

def ctl(action,name,*args):
    run(['python3',helper,action,'--out',croot+'/'+name,*args],action+'-'+name.replace('/','-')+'.log')

error=None
try:
    ctl('freeze','frozen','--case',croot+'/case.json')
    case['metadata']=croot+'/frozen/metadata.json'
    (out/'case.json').write_text(json.dumps(case,indent=2)+'\n')
    ctl('clone','database.json','--database',db)
    ctl('start','app.json','--case',croot+'/case.json','--database',db,'--port','3030')
    env=['env','BASE=http://127.0.0.1:3030','JWT_SECRET=multicore-server-challenge',
         'DATABASE_URL=postgres://conduit:conduit@127.0.0.1:5432/'+db,
         'PGHOST=127.0.0.1','PGUSER=postgres','PGPASSWORD=challenge-test-only']
    race=['python3','/comparison/optimization/tests/article-update-race.py']
    if a.baseline:
        race+=['--expect-stale']
    race+=['--out',croot+'/article-races.json']
    run([*env,*race],'article-races.log')
    result=json.loads((out/'article-races.json').read_text())
    assert result['pass'],result
    print(json.dumps({'article_races':'baseline_defects_reproduced' if a.baseline else 'fixed_pass'}),flush=True)
    password=['python3','/comparison/optimization/tests/password-nul-probe.py']
    if a.baseline:
        password+=['--expect-rejected']
    else:
        password+=['--go-helper','go','run','/comparison/optimization/tests/bcrypt-passwords.go']
    password+=['--out',croot+'/password-nul.json']
    run([*env,*password],'password-nul.log')
    result=json.loads((out/'password-nul.json').read_text())
    assert result['pass'],result
    print(json.dumps({'password_nul':'baseline_defect_reproduced' if a.baseline else 'Go_interop_pass'}),flush=True)
except BaseException as exc:
    error=type(exc).__name__+': '+str(exc)
finally:
    if (out/'app.json').exists():
        try:
            ctl('stop','stopped.json','--case',croot+'/app.json')
        except Exception as exc:
            error=(error or '')+' stop:'+str(exc)
    if (out/'database.json').exists():
        try:
            ctl('drop','dropped.json','--database',db)
        except Exception as exc:
            error=(error or '')+' drop:'+str(exc)
    (out/'result.json').write_text(json.dumps({'pass':error is None,'error':error,
                 'baseline_reproduction':a.baseline,'implementation_correct':error is None and not a.baseline},indent=2)+'\n')
print(json.dumps({'output':str(out),'pass':error is None,'error':error}),flush=True)
raise SystemExit(1 if error else 0)
