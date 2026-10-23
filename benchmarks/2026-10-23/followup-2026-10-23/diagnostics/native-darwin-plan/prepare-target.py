#!/usr/bin/env python3
"""Create a stopped-data checkpoint and an owned, loopback-published target; no host settings change."""
import datetime, hashlib, json, socket, subprocess, time
from pathlib import Path
ROOT=Path('/private/tmp/multicore-optimize-20261023/diagnostics/native-darwin-plan/target-preparation-20261023')
OLD='multicore-comparison-target-20261023'
NEW='multicore-native-target-20261023'
IMAGE='multicore-native-checkpoint:20261023'

def main():
 ROOT.mkdir(exist_ok=False)
 operations=[]
 def save(): (ROOT/'operations.json').write_text(json.dumps(operations,indent=2)+'\n')
 def run(argv,timeout=120):
  before=time.time_ns()
  r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
  operations.append(dict(argv=argv,start_wall_ns=before,end_wall_ns=time.time_ns(),exit=r.returncode,stdout=r.stdout,stderr=r.stderr));save()
  if r.returncode:raise RuntimeError(str(argv)+': '+r.stderr)
  return r.stdout
 power=run(['pmset','-g','batt'])
 assert 'AC Power' in power and 'discharging' not in power.lower()
 inspect=json.loads(run(['docker','inspect',OLD]))[0]
 assert inspect['HostConfig']['NanoCpus']==8000000000
 assert inspect['HostConfig']['Memory']==16*1024**3 and inspect['HostConfig']['MemorySwap']==16*1024**3
 assert inspect['HostConfig']['CpusetCpus']==''
 (ROOT/'original-inspect.json').write_text(json.dumps(inspect,indent=2)+'\n')
 for port in range(33000,33016):
  with socket.socket() as sock:sock.bind(('127.0.0.1',port))
 run(['docker','exec','--user','root',OLD,'python3','/evidence/lab-target-control-v2.py','snapshot','--out','/comparison/optimization/diagnostics/native-darwin-plan/target-preparation-20261023/old-before.json'])
 run(['docker','exec','--user','root',OLD,'pg_ctlcluster','18','main','stop','--mode','fast'])
 run(['docker','stop','--timeout','10',OLD])
 image=run(['docker','commit',OLD,IMAGE],timeout=240).strip()
 argv=['docker','run','-d','--name',NEW,'--label','multicore.local.owner=native-darwin-diagnostic-20261023','--cpus','8','--memory',str(16*1024**3),'--memory-swap',str(16*1024**3),'--ulimit','nofile=200000:200000']
 for port in range(33000,33016):argv+=['--publish',f'127.0.0.1:{port}:3000']
 for mount in inspect['Mounts']:
  assert mount['Type']=='bind'
  argv+=['--mount','type=bind,src='+mount['Source']+',dst='+mount['Destination']+('' if mount['RW'] else ',readonly')]
 argv+=['--entrypoint','/bin/sh',IMAGE,'-c','exec sleep infinity']
 run(argv)
 new=json.loads(run(['docker','inspect',NEW]))[0]
 hc=new['HostConfig']
 assert hc['NanoCpus']==8000000000 and hc['Memory']==16*1024**3 and hc['MemorySwap']==16*1024**3 and hc['CpusetCpus']==''
 mappings=hc['PortBindings']['3000/tcp']
 assert {(x['HostIp'],int(x['HostPort'])) for x in mappings}=={('127.0.0.1',x) for x in range(33000,33016)}
 (ROOT/'new-inspect.json').write_text(json.dumps(new,indent=2)+'\n')
 run(['docker','exec','--user','root',NEW,'pg_ctlcluster','18','main','start'])
 run(['docker','exec','--user','root',NEW,'python3','/evidence/lab-target-control-v2.py','snapshot','--out','/comparison/optimization/diagnostics/native-darwin-plan/target-preparation-20261023/new-after.json'])
 a=json.loads((ROOT/'old-before.json').read_text());b=json.loads((ROOT/'new-after.json').read_text())
 assert a['pg_settings']==b['pg_settings']
 assert a['official_source_sha256']==b['official_source_sha256']
 proof=dict(status='PREPARED_NOT_BENCHMARKED',old_target=OLD,new_target=NEW,image=image,old_preserved_stopped=True,server_cpus=8,server_memory_bytes=16*1024**3,no_swap=True,no_affinity=True,original_pg_settings_equal=True,original_sources_equal=True,loopback_ports=list(range(33000,33016)),host_settings_changed=False)
 (ROOT/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps(proof))
if __name__=='__main__':main()
