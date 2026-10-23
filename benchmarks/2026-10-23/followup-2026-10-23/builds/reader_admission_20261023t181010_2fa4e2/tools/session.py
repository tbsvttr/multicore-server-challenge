import argparse,contextlib,json,os,pathlib,pwd,resource,subprocess,time,urllib.request
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
text=pathlib.Path('/proc/'+str(child.pid)+'/stat').read_text();state['launcher_start_ticks']=int(text[text.rindex(')')+2:].split()[19]);(root/(role+'-state.json')).write_text(json.dumps(state,indent=2)+'\n')
if role=='probe':
 code=child.wait();(root/'probe-exit.json').write_text(json.dumps({'exit':code})+'\n');raise SystemExit(code)
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
