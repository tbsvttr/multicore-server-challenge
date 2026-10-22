#!/usr/bin/env python3
"""Owned sequential health/actual-NOFILE verification; never loads or compiles."""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--attempt',required=True)
a=p.parse_args()
assert a.attempt.replace('-','').isalnum()
r=pathlib.Path(__file__).resolve().parent.parent
out=r/'nofile-v2'/a.attempt
out.mkdir(exist_ok=False)
(out/'tools').mkdir();(out/'frozen').mkdir()
helper=out/'tools/lab-target-control-v2.py'
shutil.copy2(r/'lab-target-control-v2.py',helper)
base='/evidence/nofile-v2/'+a.attempt
remote=base+'/tools/lab-target-control-v2.py'
target='multicore-goose-dev-20261022'

def run(args,log):
    proc=subprocess.run(['docker','exec','--user','root',target,*args],text=True,capture_output=True,timeout=180)
    (out/log).write_text(proc.stdout+proc.stderr)
    if proc.returncode:raise RuntimeError(str(args)+' exited '+str(proc.returncode)+'\n'+proc.stdout[-1500:]+proc.stderr[-1500:])
    return proc.stdout

def control(action,path,*args):
    return run(['python3',remote,action,'--out',base+'/'+path,*args],path+'.command.log')

cases={}
for name in ['rust-goose-80k-plan.json','pr31-goose-80k-plan.json']:
    for case in json.loads((r/name).read_text())['configuration']['cases']:
        if case['name'] in cases:assert cases[case['name']]==case
        cases[case['name']]=dict(case)
control('probe-limits','limit-probe.json')
results=[]
for index,name in enumerate(['rust7','goose','goose31_portable']):
    case=cases[name]
    (out/(name+'.json')).write_text(json.dumps(case,indent=2)+'\n')
    control('freeze','frozen/'+name,'--case',base+'/'+name+'.json')
    meta=json.loads((out/'frozen'/name/'metadata.json').read_text())
    assert meta['binary_sha256']==case['expected_binary_sha256']
    case['metadata']=base+'/frozen/'+name+'/metadata.json'
    (out/(name+'.json')).write_text(json.dumps(case,indent=2)+'\n')
    attempt=out/name;attempt.mkdir()
    db='mc_pair_nofile_v2_'+str(index)+'_'+str(int(time.time()))
    state={'case':name,'binary_sha256':meta['binary_sha256'],'database':db,'pass':False}
    try:
        control('clone',name+'/database.json','--database',db)
        control('start',name+'/app.json','--database',db,'--case',base+'/'+name+'.json','--port','3000')
        program="import http.client,json;out=[]\nfor i in range(1,5):\n c=http.client.HTTPConnection('127.0.0.'+str(i),3000,timeout=3);c.request('GET','/api/tags');v=c.getresponse();b=json.loads(v.read());out.append({'host':'127.0.0.'+str(i),'status':v.status,'tags_count':len(b['tags'])});c.close()\nassert all(x['status']==200 for x in out);print(json.dumps(out))"
        state['health_addresses']=json.loads(run(['python3','-c',program],name+'/four-address-health.json'))
        control('snapshot',name+'/snapshot.json','--case',base+'/'+name+'/app.json')
        snap=json.loads((attempt/'snapshot.json').read_text())
        witness=snap['actual_app'];actual=witness['processes'][0]
        assert witness['valid'] and actual['uid']==501 and actual['nofile_soft']>=200000 and actual['nofile_hard']>=200000 and snap['app_healthy']
        state.update({'pass':True,'actual_pid':actual['pid'],'uid':actual['uid'],
                      'nofile_soft':actual['nofile_soft'],'nofile_hard':actual['nofile_hard']})
    except Exception as e:
        state['error']=str(e)
    finally:
        if (attempt/'app.json').exists():control('stop',name+'/stopped.json','--case',base+'/'+name+'/app.json')
        control('drop',name+'/dropped.json','--database',db)
        state['stopped_and_dropped']=True
    results.append(state)
    print(json.dumps(state),flush=True)
    (out/'results-so-far.json').write_text(json.dumps(results,indent=2)+'\n')
proof={'scope':'sequential health and actual-process resource verification only; no load or compilation',
       'helper_sha256':hashlib.sha256(helper.read_bytes()).hexdigest(),
       'verifier_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
       'all_passed':len(results)==3 and all(x['pass'] for x in results),'results':results}
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
raise SystemExit(0 if proof['all_passed'] else 1)
