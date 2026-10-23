#!/usr/bin/env python3
"""Verify completed artifacts only; no process/network/database operations."""
import collections
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent
read=lambda name:json.loads((root/name).read_text())
sha=lambda raw:hashlib.sha256(raw).hexdigest()
checks=[]
def check(name,condition):
    checks.append({'check':name,'pass':bool(condition)})
    if not condition:raise AssertionError(name)
result,probe,metadata=read('result.json'),read('probe.json'),read('frozen/metadata.json')
expected='9016ff93e924c0d94652490ac895d1fbc64153fd9d3ea4b8b52b66ae892c3424'
check('execution_and_fixture_checks_pass',result['pass'] and probe['pass'] and len(probe['checks'])==26 and all(c['pass'] for c in probe['checks']))
check('frozen_binary_present_and_exact',sha((root/'frozen/app').read_bytes())==expected==metadata['binary_sha256']==result['binary_sha256_after']==result['frozen_binary_sha256_after'])
check('pre_post_source_identical',read('source-before.json')==read('source-after.json')==metadata['source_sha256'] and result['source_unchanged'])
check('frozen_source_bytes_match',all(sha((root/'frozen/source'/name).read_bytes())==value for name,value in metadata['source_sha256'].items()))
check('all_frozen_tools_match',all(sha((root/'tools'/name).read_bytes())==value for name,value in read('tool-sha256.json').items()))
for role in ['app','proxy']:
    actual=read(role+'-actual.json');state=read(role+'-state.json');stop=read(role+'-stopped.json')
    check(role+'_normal_uid_and_nofile',actual['valid'] and actual['expected_uid']==501 and len(actual['processes'])==1 and all(x==501 for x in actual['processes'][0]['uids']) and actual['processes'][0]['nofile_soft']==200000 and actual['processes'][0]['nofile_hard']==200000)
    check(role+'_owned_group_stopped',state['pgid']==stop['stopped_pgid'] and actual['processes'][0]['pid'] in stop['members_before'])
check('owned_probe_group_stopped',read('probe-stopped.json')['stopped_pgid']==read('probe-state.json')['pgid'])
check('owned_clone_dropped',read('dropped.json')=={'database':result['database'],'dropped':True} and probe['fixture_cleaned'])
check('charging_all_recorded_samples',len(result['power'])>=2 and all(p['charging'] for p in result['power']))
for name in ['target-before.json','target-after.json']:
    target=read(name);cfg=target['HostConfig']
    check(name+'_resources',cfg['NanoCpus']==8000000000 and cfg['Memory']==17179869184 and cfg['MemorySwap']==17179869184 and not cfg['CpusetCpus'])
check('target_identity_unchanged',read('target-before.json')['Id']==read('target-after.json')['Id'])
wire=(root/'wire.jsonl').read_bytes();receipt=probe['wire_receipt']
check('observed_wire_prefix_hash',sha(wire[:receipt['observed_prefix_bytes']])==receipt['observed_prefix_sha256'])
events=[json.loads(line) for line in wire.splitlines()]
check('observer_completed_without_error',events[-1]['event']=='observer_stopped' and not any(e['event']=='observer_error' for e in events))
state={};max_groups=max_exec=0;reader_binds=reader_execs=0
for event in events:
    kind=event['event']
    if kind=='connection':state[event['connection']]={'writer':event['writer'],'groups':0,'binds':0,'execs':0}
    elif kind=='bind':state[event['connection']]['binds']+=1
    elif kind=='sync':
        c=state[event['connection']];c['groups']+=1;c['execs']+=event['executions']
        check('sync_credit_'+str(event['connection'])+'_'+str(event['monotonic']),c['groups']==event['outstanding'])
        if not c['writer']:
            max_groups=max(max_groups,c['groups']);max_exec=max(max_exec,event['executions'])
            check('reader_bound_'+str(event['monotonic']),c['groups']<=1 and event['executions']<=4)
    elif kind=='ready':
        c=state[event['connection']];c['groups']-=1
        check('ready_credit_'+str(event['connection'])+'_'+str(event['monotonic']),c['groups']==event['outstanding'] and c['groups']>=0)
    elif kind=='closed':check('closed_credit_'+str(event['connection']),state[event['connection']]['groups']==event['outstanding']==0)
check('one_reader_one_writer',len(state)==2 and sum(not c['writer'] for c in state.values())==1)
check('all_bind_execute_groups_complete',all(c['groups']==0 and c['binds']==c['execs'] for c in state.values()))
check('cap1_and_sync4_exercised',max_groups==1 and max_exec==4)
binds=[e for e in events if e['event']=='bind']
parameters={x for e in binds for x in e['parameter_sha256']+e['array_element_sha256'] if x}
check('all_24_abandoned_slugs_absent',all(sha((probe['nonce']+'_abandon_'+str(i)).encode()) not in parameters for i in range(24)))
slug=sha((probe['nonce']+'_write').encode())
for statement in ['s19','s17']:
    check(statement+'_bound_once',sum(e['writer'] and e['statement']==statement and slug in e['parameter_sha256'] for e in binds)==1)
output={'status':'PASS','scope':'Offline audit of completed correctness artifacts only; not capacity/performance/rank proof',
        'checks':checks,'passed':len(checks),'failed':0,'binary_present_during_verification':True,
        'expected_binary_sha256':expected,'wire_event_counts':dict(collections.Counter(e['event'] for e in events)),
        'reader_max_outstanding_groups':max_groups,'reader_max_executions_per_sync':max_exec,
        'abandoned_slug_count':24,'flood_successful_requests':sum(x['completed'] for c in probe['checks'] if c['check']=='mixed_arrival_workers_complete' for x in c['flood']),
        'limitations':['No proof every abandoned HTTP request was parsed before close.','Correctness fixture only; source remains an unpromoted prototype.','Verifier requires original frozen binary; text export must preserve this pre-export receipt.']}
(root/'saved-verification.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps({k:output[k] for k in ['status','passed','failed','reader_max_outstanding_groups','reader_max_executions_per_sync']}))
