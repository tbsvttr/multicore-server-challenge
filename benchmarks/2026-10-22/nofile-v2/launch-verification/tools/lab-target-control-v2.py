#!/usr/bin/env python3
"""Owned process/database lifecycle for the combined local target container."""
import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import pwd
import re
import shutil
import signal
import subprocess
import time
import urllib.request

p = argparse.ArgumentParser()
p.add_argument('action', choices=['freeze', 'clone', 'drop', 'start', 'stop', 'snapshot', 'probe-limits'])
p.add_argument('--case')
p.add_argument('--out', required=True)
p.add_argument('--database')
p.add_argument('--template', default='conduit_seed')
p.add_argument('--user', default='challenge')
p.add_argument('--port', type=int, default=3000)
p.add_argument('--secret', default='multicore-server-challenge')
a = p.parse_args()
out = pathlib.Path(a.out)

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def dbid(s):
    if not re.fullmatch(r'mc_pair_[a-z0-9_]{1,52}', s or ''):
        raise ValueError('only an owned mc_pair_ database name is allowed')
    return s

def psql(s, database='postgres'):
    r = subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-A','-t','-v','ON_ERROR_STOP=1','-d',database,'-c',s],
                       text=True,capture_output=True,timeout=120)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()

def enough_nofile(value):
    return value=='unlimited' or isinstance(value,int) and value>=200000

def actual_app_witness(state):
    expected_uid=state['app_uid']
    expected_exe=os.path.realpath(state['frozen_binary'])
    matches=[]
    for path in pathlib.Path('/proc').glob('[0-9]*/stat'):
        try:
            text=path.read_text();fields=text[text.rindex(')')+2:].split()
            pid=int(path.parent.name)
            if int(fields[2])!=state['pgid'] or fields[0]=='Z':continue
            if os.path.realpath(path.parent/'exe')!=expected_exe:continue
            status=(path.parent/'status').read_text()
            uids=[int(x) for x in next(line for line in status.splitlines() if line.startswith('Uid:')).split()[1:]]
            limits=(path.parent/'limits').read_text()
            line=next(line for line in limits.splitlines() if line.startswith('Max open files'))
            soft,hard=re.match(r'^Max open files\s+(\S+)\s+(\S+)',line).groups()
            soft=int(soft) if soft.isdigit() else soft
            hard=int(hard) if hard.isdigit() else hard
            matches.append({'pid':pid,'pgid':int(fields[2]),'start_ticks':int(fields[19]),'exe':expected_exe,
                            'uid':uids[1],'uids':uids,'nofile_soft':soft,'nofile_hard':hard,
                            'proc_limits':limits,'proc_status':status})
        except (OSError,ValueError,IndexError,StopIteration,AttributeError):continue
    result={'valid':False,'expected_uid':expected_uid,'minimum_nofile':200000,'processes':matches,'reasons':[]}
    if len(matches)!=1:
        result['reasons'].append('expected exactly one live actual app executable in the owned process group')
        return result
    proc=matches[0]
    if any(uid!=expected_uid for uid in proc['uids']):result['reasons'].append('actual app UID differs from the normal user')
    if not enough_nofile(proc['nofile_soft']) or not enough_nofile(proc['nofile_hard']):
        result['reasons'].append('actual app NOFILE soft or hard limit is below200000')
    if state.get('actual_app_pid') is not None:
        if proc['pid']!=state['actual_app_pid'] or proc['start_ticks']!=state['actual_app_start_ticks']:
            result['reasons'].append('actual app process identity changed after startup')
    result['valid']=not result['reasons']
    return result

if a.action == 'probe-limits':
    program="import json,os,resource;print(json.dumps({'uid':os.getuid(),'euid':os.geteuid(),'nofile':resource.getrlimit(resource.RLIMIT_NOFILE)}))"
    probes={}
    for name,wrapper in [('runuser',['runuser','-u',a.user,'--']),
                         ('runuser_prlimit',['runuser','-u',a.user,'--','prlimit','--nofile=200000:200000','--'])]:
        r=subprocess.run([*wrapper,'python3','-c',program],text=True,capture_output=True,timeout=10)
        probes[name]={'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
        if r.returncode==0:probes[name]['actual']=json.loads(r.stdout)
    out.write_text(json.dumps(probes,indent=2)+'\n')
    wrapped=probes['runuser_prlimit']
    assert wrapped['exit']==0 and wrapped['actual']['uid']==pwd.getpwnam(a.user).pw_uid,wrapped
    assert all(value>=200000 for value in wrapped['actual']['nofile']),wrapped
elif a.action == 'freeze':
    case = json.loads(pathlib.Path(a.case).read_text())
    src = pathlib.Path(case['binary'])
    out.mkdir(exist_ok=False)
    frozen = out/'app'
    shutil.copy2(src,frozen)
    frozen.chmod(0o755)
    manifest = {}
    root = pathlib.Path(case['source_dir'])
    source_copy = out/'source'
    source_copy.mkdir()
    skip = {'.git','.goose','.goose-home','.build','.deps','bin','target','node_modules','__pycache__'}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            file = pathlib.Path(base)/f
            if file.is_file():
                manifest[str(file.relative_to(root))] = digest(file)
                copied = source_copy/file.relative_to(root)
                copied.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(file,copied)
    metadata = {'case':case,'binary_sha256':digest(src),'frozen_binary':str(frozen),
                'source_sha256':manifest,'source_manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()}
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata))
elif a.action == 'clone':
    db = dbid(a.database)
    assert a.template == 'conduit_seed', 'paired protocol requires the original full-seed template'
    psql(f'CREATE DATABASE {db} TEMPLATE conduit_seed STRATEGY FILE_COPY')
    text = psql("SELECT json_build_object('users',(SELECT count(*) FROM users),'articles',(SELECT count(*) FROM articles),'size_bytes',pg_database_size(current_database()))",db)
    counts = json.loads(text)
    assert counts['users']==100000 and counts['articles']==500000,counts
    out.write_text(json.dumps({'database':db,'template':a.template,'counts':counts},indent=2)+'\n')
elif a.action == 'drop':
    db = dbid(a.database)
    psql(f'DROP DATABASE {db} WITH (FORCE)')
    out.write_text(json.dumps({'database':db,'dropped':True})+'\n')
elif a.action == 'snapshot':
    snap = {'wall_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),'uname':list(os.uname()),
            'pg_settings':json.loads(psql("SELECT json_agg(json_build_object('name',name,'setting',setting,'unit',unit,'source',source)) FROM pg_settings"))}
    repo=pathlib.Path('/work')
    upstream=subprocess.run(['git','-c','safe.directory=/work','-C','/work','rev-parse','HEAD'],text=True,capture_output=True)
    snap['repo_head']={'exit':upstream.returncode,'stdout':upstream.stdout.strip(),'stderr':upstream.stderr.strip()}
    files=[repo/n for n in ['README.md','SPEC.md','WORKLOAD.md','schema.sql','test/run.sh','seed/make-seed.sh','box/pg-conf.sh']]
    files.extend(p for p in (repo/'bench').rglob('*') if p.is_file() and p.suffix in {'.go','.mod','.sum'})
    snap['official_source_sha256']={str(f.relative_to(repo)):digest(f) for f in files}
    for name in ['cpu.max','cpuset.cpus','cpuset.cpus.effective','memory.max','memory.swap.max','memory.events','cpu.stat','memory.current']:
        path=pathlib.Path('/sys/fs/cgroup')/name
        snap[name]=path.read_text().strip() if path.exists() else None
    for name in ['ip_local_port_range','tcp_fin_timeout']:
        path=pathlib.Path('/proc/sys/net/ipv4')/name
        snap[name]=path.read_text().strip() if path.exists() else None
    if a.case:
        state=json.loads(pathlib.Path(a.case).read_text())
        snap['app_pgid']=state['pgid']
        snap['actual_app']=actual_app_witness(state)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{state['port']}/api/tags",timeout=3) as r:
                snap['app_healthy']=r.status==200
        except OSError as e:
            snap['app_healthy']=False
            snap['app_health_error']=str(e)
    out.write_text(json.dumps(snap,indent=2)+'\n')
elif a.action == 'start':
    case = json.loads(pathlib.Path(a.case).read_text())
    metadata = json.loads(pathlib.Path(case['metadata']).read_text())
    binary = metadata['frozen_binary']
    assert digest(binary)==metadata['binary_sha256'],'frozen binary changed'
    db = dbid(a.database)
    env = os.environ.copy()
    env.update({'DATABASE_URL':f'postgres://conduit:conduit@127.0.0.1:5432/{db}',
                'JWT_SECRET':a.secret,'HOST':'0.0.0.0','PORT':str(a.port)})
    env.update(case.get('env',{}))
    for protected in ['DATABASE_URL','JWT_SECRET','HOST','PORT']:
        assert protected not in case.get('env',{}),'case cannot override shared runtime contract'
    logfile = out.parent/'server.log'
    with logfile.open('x') as log:
        proc = subprocess.Popen(['runuser','-u',a.user,'--','prlimit','--nofile=200000:200000','--',binary],cwd=case.get('workdir',case['source_dir']),
                                env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    state = {'launcher_pid':proc.pid,'pgid':proc.pid,'frozen_binary':binary,'binary_sha256':metadata['binary_sha256'],
             'app_user':a.user,'app_uid':pwd.getpwnam(a.user).pw_uid,
             'launch_wrapper':['runuser','-u',a.user,'--','prlimit','--nofile=200000:200000','--'],
             'database':db,'port':a.port,'env':{k:env[k] for k in ['DATABASE_URL','JWT_SECRET','HOST','PORT',*case.get('env',{})]},
             'start_wall_ns':time.time_ns(),'start_monotonic_ns':time.monotonic_ns()}
    stat=pathlib.Path(f'/proc/{proc.pid}/stat').read_text()
    state['launcher_start_ticks']=int(stat[stat.rindex(')')+2:].split()[19])
    out.write_text(json.dumps(state,indent=2)+'\n')
    for _ in range(60):
        if proc.poll() is not None:
            raise RuntimeError(f'app exited {proc.returncode}; see {logfile}')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{a.port}/api/tags',timeout=1) as r:
                if r.status==200:
                    witness=actual_app_witness(state)
                    state['actual_app']=witness
                    out.write_text(json.dumps(state,indent=2)+'\n')
                    assert witness['valid'],witness
                    actual=witness['processes'][0]
                    state['actual_app_pid']=actual['pid'];state['actual_app_start_ticks']=actual['start_ticks']
                    out.write_text(json.dumps(state,indent=2)+'\n')
                    (out.parent/'app-process-limits.txt').write_text(actual['proc_limits'])
                    (out.parent/'app-process-status.txt').write_text(actual['proc_status'])
                    print(json.dumps({'healthy':True,'pgid':proc.pid,'actual_app_pid':actual['pid'],
                                      'uid':actual['uid'],'nofile_soft':actual['nofile_soft'],'nofile_hard':actual['nofile_hard']}));break
        except OSError:
            pass
        time.sleep(1)
    else:
        raise TimeoutError('owned app did not become healthy in60s')
elif a.action == 'stop':
    state=json.loads(pathlib.Path(a.case).read_text())
    leader=pathlib.Path(f"/proc/{state['launcher_pid']}/stat")
    if leader.exists():
        stat=leader.read_text()
        assert int(stat[stat.rindex(')')+2:].split()[19])==state['launcher_start_ticks'],'launcher PID was reused'
    members=[]
    for path in pathlib.Path('/proc').glob('[0-9]*/stat'):
        with contextlib.suppress(OSError,ValueError,IndexError):
            text=path.read_text();parts=text[text.rindex(')')+2:].split()
            if int(parts[2])==state['pgid'] and parts[0]!='Z': members.append(int(path.parent.name))
    if members:
        os.killpg(state['pgid'],signal.SIGTERM)
        time.sleep(2)
        with contextlib.suppress(ProcessLookupError): os.killpg(state['pgid'],signal.SIGKILL)
    out.write_text(json.dumps({'stopped_pgid':state['pgid'],'members_before':members})+'\n')
