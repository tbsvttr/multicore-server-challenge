import json,pathlib,subprocess,sys,time
root=pathlib.Path(sys.argv[1]);app=json.loads((root/'app.json').read_text())
with (root/'target-monitor.log').open('x') as log:
 p=subprocess.Popen(['python3',str(root/'tools/target_monitor.py'),'--out',str(root/'target-monitor.jsonl'),'--stop',str(root/'target-monitor.stop'),'--app-pgid',str(app['pgid'])],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
text=pathlib.Path('/proc/'+str(p.pid)+'/stat').read_text();state={'launcher_pid':p.pid,'pgid':p.pid,'launcher_start_ticks':int(text[text.rindex(')')+2:].split()[19])};(root/'monitor-state.json').write_text(json.dumps(state)+'\n')
code=p.wait();(root/'monitor-exit.json').write_text(json.dumps({'exit':code})+'\n')
