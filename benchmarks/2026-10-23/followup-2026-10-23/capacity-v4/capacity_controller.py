#!/usr/bin/env python3
"""Prepare or explicitly execute a finite local ARM capacity search.

Preparing a plan performs no Docker/network operations. Execution creates one
owned client container and one fresh full-seed app session per declared case.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

from search_policy import DEFAULT_PROTOCOL, client_gomaxprocs, client_cpu_scope_policy, growth_factor, load_cpus, load_memory_bytes, next_action, shards
from audit.evidence import audit_phase
from audit.primitives import inspect_budget, read, sha


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def database_name(run_name, case_index):
    return 'mc_pair_' + run_name.split('_', 1)[1].replace('t', '_') + '_' + str(case_index)


def prepare(config_path, plan_path):
    if plan_path.exists() or plan_path.with_suffix(plan_path.suffix + '.sha256').exists():
        raise FileExistsError('refusing to replace a frozen plan')
    cfg = read(config_path)
    cfg.setdefault('target_container', 'multicore-comparison-target-20261023')
    cfg.setdefault('host_evidence', '/private/tmp/multicore-comparison-20261023')
    cfg.setdefault('container_evidence', '/comparison')
    cfg.setdefault('old_host_evidence', '/private/tmp/multicore-research-20261022')
    cfg.setdefault('native_binary', '/evidence/tools/loadgen')
    cfg.setdefault('expected_native_sha256', '886eaa564c6cdab1a791534d6931d1b8eb9b5c21d1e1ebaaa2824616c4562cdb')
    cfg.setdefault('jwt_secret', 'multicore-server-challenge')
    cfg.setdefault('port', 3000)
    cfg.setdefault('lifecycle_helper', '/private/tmp/multicore-research-20261022/lab-target-control-v2.py')
    cfg.setdefault('monitor_helper', '/private/tmp/multicore-research-20261022/lab-monitor.py')
    cfg.setdefault('load_memory_bytes', DEFAULT_PROTOCOL['load_memory_bytes'])
    cfg.setdefault('load_cpus', DEFAULT_PROTOCOL['load_cpus'])
    cfg.setdefault('client_cpu_scope_policy', DEFAULT_PROTOCOL['client_cpu_scope_policy'])
    cfg.setdefault('growth_factor', DEFAULT_PROTOCOL['growth_factor'])
    names = []
    for case in cfg['cases']:
        name = case['name']
        assert name.replace('_', '').replace('-', '').isalnum() and len(name) <= 32
        assert case['binary'].startswith('/') and case['source_dir'].startswith('/')
        assert len(case['expected_binary_sha256']) == 64
        assert all(c in '0123456789abcdef' for c in case['expected_binary_sha256'])
        assert not {'DATABASE_URL', 'JWT_SECRET', 'HOST', 'PORT'} & set(case.get('env', {}))
        case.setdefault('env', {})
        names.append(name)
    assert names and len(names) == len(set(names))
    protocol = json.loads(json.dumps(DEFAULT_PROTOCOL))
    protocol['load_memory_bytes'] = cfg['load_memory_bytes']
    protocol['load_cpus'] = cfg['load_cpus']
    protocol['client_cpu_scope_policy'] = cfg['client_cpu_scope_policy']
    protocol['growth_factor'] = cfg['growth_factor']
    client_gomaxprocs(protocol, cfg)
    growth_factor(protocol, cfg)
    client_cpu_scope_policy(protocol, cfg)
    load_memory_bytes(protocol, cfg)
    for key, value in cfg.pop('search_overrides', {}).items():
        assert key in ['start_users', 'max_users', 'max_probes', 'max_holds'], 'only search bounds may be overridden'
        protocol[key] = int(value)
    assert 10 <= protocol['start_users'] <= protocol['max_users'] <= 160000
    assert 1 <= protocol['max_probes'] <= 20 and 1 <= protocol['max_holds'] <= 8
    plan = {'schema': 'multicore-local-capacity-v4',
            'scope': 'Local shared ARM64 Mac/Docker capacity search; no official x86 rank or all-competitor claim.',
            'configuration': cfg, 'protocol': protocol,
            'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'source_config_sha256': sha(config_path)}
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    write(plan_path, plan)
    plan_path.with_suffix(plan_path.suffix + '.sha256').write_text(sha(plan_path) + '\n')
    print(json.dumps({'prepared_plan': str(plan_path), 'sha256': sha(plan_path), 'cases': names,
                      'protocol': protocol, 'executed': False}))


class Controller:
    def __init__(self, plan_path):
        self.plan_path, self.plan = plan_path, read(plan_path)
        assert self.plan['schema'] == 'multicore-local-capacity-v4'
        assert sha(plan_path) == plan_path.with_suffix(plan_path.suffix + '.sha256').read_text().strip()
        self.cfg, self.protocol = self.plan['configuration'], self.plan['protocol']
        for name in ['warmup_users', 'warmup', 'probe', 'hold', 'target_cpus', 'target_memory_bytes',
                     'max_users_per_shard', 'max_shards', 'gomaxprocs_per_shard', 'resolution', 'load_cpu_limit_pct', 'rounding_policy']:
            assert self.protocol[name] == DEFAULT_PROTOCOL[name], 'normal protocol changed: ' + name
        client_gomaxprocs(self.protocol, self.cfg)
        self.load_memory = load_memory_bytes(self.protocol, self.cfg)
        self.load_cpus = load_cpus(self.protocol, self.cfg)
        self.cpu_scope_policy = client_cpu_scope_policy(self.protocol, self.cfg)
        growth_factor(self.protocol, self.cfg)
        self.target = self.cfg['target_container']
        stamp = time.strftime('%Y%m%dT%H%M%S', time.gmtime()).lower()
        self.name = 'capacity_' + stamp + '_' + os.urandom(3).hex()
        self.host_base = Path(self.cfg['host_evidence'])
        self.root = self.host_base / 'optimization' / self.name
        self.root.mkdir(parents=True, exist_ok=False)
        self.croot = self.cfg['container_evidence'].rstrip('/') + '/optimization/' + self.name
        self.client = 'multicore-capacity-client-' + stamp + '-' + os.urandom(3).hex()
        self.events = (self.root / 'events.jsonl').open('x')
        self.load_created = False
        self.stop_host = threading.Event()
        self.current_generators = []
        self.case_records = []
        write(self.root / 'plan.json', self.plan)
        (self.root / 'plan.sha256').write_text(sha(plan_path) + '\n')
        tools = self.root / 'tools'
        (tools / 'audit').mkdir(parents=True)
        here = Path(__file__).resolve().parent
        for source, destination in [(here / 'capacity_controller.py', tools / 'capacity_controller.py'),
                                    (here / 'search_policy.py', tools / 'search_policy.py'),
                                    (Path(self.cfg['lifecycle_helper']), tools / 'target_helper.py'),
                                    (Path(self.cfg['monitor_helper']), tools / 'monitor.py')]:
            shutil.copy2(source, destination)
        for source in (here / 'audit').glob('*.py'):
            shutil.copy2(source, tools / 'audit' / source.name)
        write(self.root / 'tool-sha256.json', {str(p.relative_to(tools)): sha(p) for p in tools.rglob('*') if p.is_file()})
        self.helper = self.croot + '/tools/target_helper.py'
        self.monitor_helper = self.croot + '/tools/monitor.py'

    def event(self, name, **data):
        row = {'event': name, 'wall_ns': time.time_ns(), 'monotonic_ns': time.monotonic_ns(), **data}
        self.events.write(json.dumps(row) + '\n'); self.events.flush()
        print(json.dumps(row), flush=True)

    def command(self, argv, save=None, allowed=(0,), timeout=180):
        result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
        if save:
            save.write_text(result.stdout + result.stderr)
        if result.returncode not in allowed:
            raise RuntimeError(f'command exited{result.returncode}: {argv!r}\n{result.stdout[-1000:]}\n{result.stderr[-1000:]}')
        return result

    def docker(self, *argv, **kwargs):
        return self.command(['docker', *argv], **kwargs)

    def control(self, action, out, *args, **kwargs):
        return self.docker('exec', '--user', 'root', self.target, 'python3', self.helper,
                           action, '--out', out, *args, **kwargs)

    def inspect(self, name, path, cpus, memory):
        obj = json.loads(self.docker('inspect', name).stdout)[0]
        write(path, obj)
        assert inspect_budget(obj, cpus, memory), 'actual cgroup budget or affinity differs'
        return obj

    def host_monitor(self):
        with (self.root / 'host-memory.jsonl').open('x') as stream:
            tick = 0
            while not self.stop_host.is_set():
                began = time.monotonic()
                row = {'wall_ns': time.time_ns(), 'monotonic_ns': time.monotonic_ns()}
                for name, argv in [('vm_stat', ['vm_stat']), ('swapusage', ['sysctl', 'vm.swapusage'])]:
                    try:
                        r = subprocess.run(argv, text=True, capture_output=True, timeout=3)
                        row[name] = {'exit': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
                    except Exception as error:
                        row[name] = {'error': str(error)}
                if tick % 10 == 0:
                    try:
                        r = subprocess.run(['memory_pressure', '-Q'], text=True, capture_output=True, timeout=3)
                        row['memory_pressure'] = {'exit': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
                    except Exception as error:
                        row['memory_pressure'] = {'error': str(error)}
                stream.write(json.dumps(row) + '\n'); stream.flush(); tick += 1
                self.stop_host.wait(max(.05, 1 - (time.monotonic() - began)))

    def idle(self, minimum):
        self.event('connection_drain_and_idle', minimum_seconds=minimum, idle_threshold_pct=15, maximum_extra_seconds=90)
        deadline = time.monotonic() + minimum
        while time.monotonic() < deadline:
            time.sleep(min(5, max(.01, deadline - time.monotonic())))
        code = "import pathlib,time,json;p=pathlib.Path('/sys/fs/cgroup/cpu.stat');get=lambda:int(dict(x.split() for x in p.read_text().splitlines())['usage_usec']);a=get();s=time.monotonic();time.sleep(1);print(json.dumps({'cpu_pct':(get()-a)/1e6/(time.monotonic()-s)/8*100}))"
        extra = time.monotonic() + 90
        while True:
            cpu = json.loads(self.docker('exec', '--user', 'root', self.target, 'python3', '-c', code).stdout)['cpu_pct']
            if cpu < 15 or time.monotonic() >= extra:
                self.event('idle_witness', cpu_pct=cpu, reached_idle=cpu < 15)
                return
            time.sleep(3)

    def kill_generators(self):
        for proc in self.current_generators:
            if proc.poll() is None:
                proc.terminate()
        code = "import pathlib,os,signal,contextlib;[(os.kill(int(p.parent.name),signal.SIGTERM)) for p in pathlib.Path('/proc').glob('[0-9]*/exe') if p.exists() and os.path.realpath(p)==" + repr(self.cfg['native_binary']) + ']'
        with contextlib.suppress(Exception):
            self.docker('exec', '--user', 'root', self.client, 'python3', '-c', code)

    def client_environment_witness(self, directory, run_id, count):
        container_code = "import os,json;print(json.dumps({'GOMAXPROCS':os.environ.get('GOMAXPROCS')}))"
        container_env = json.loads(self.docker('exec', '--user', 'root', self.client, 'python3', '-c', container_code).stdout)
        assert container_env == self.cfg['client_env'], 'container GOMAXPROCS differs'
        code = "import pathlib,os,json;binary=" + repr(self.cfg['native_binary']) + ";run=" + repr(run_id) + ";rows=[]\nfor p in pathlib.Path('/proc').glob('[0-9]*/cmdline'):\n try:\n  a=p.read_bytes().split(bytes([0]));\n  if os.path.realpath(p.parent/'exe')==binary and run.encode() in a:\n   env=dict(x.split(bytes([61]),1) for x in (p.parent/'environ').read_bytes().split(bytes([0])) if bytes([61]) in x);rows.append({'pid':int(p.parent.name),'box_index':int(a[a.index(b'-box-index')+1]),'run_id':run,'env':{'GOMAXPROCS':env.get(b'GOMAXPROCS',b'').decode()}})\n except (OSError,ValueError,IndexError): pass\nprint(json.dumps(rows))"
        deadline = time.monotonic() + 3
        while True:
            rows = json.loads(self.docker('exec', '--user', 'root', self.client, 'python3', '-c', code).stdout)
            if len(rows) == count:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('missing native process environment witnesses')
            time.sleep(.1)
        assert len({row['pid'] for row in rows}) == count
        assert sorted(row['box_index'] for row in rows) == list(range(count))
        assert all(row['run_id'] == run_id and row['env'] == self.cfg['client_env'] for row in rows)
        write(directory / 'client-env-witness.json', {'container_env': container_env, 'shards': rows})

    def phase(self, case_dir, ccase, case, action, serial):
        stage, users = action['stage'], action['users']
        name = f'{serial:02d}-{stage}-{users}'
        directory = case_dir / 'phases' / name
        directory.mkdir(parents=True, exist_ok=False)
        cdir = ccase + '/phases/' + name
        allocation = shards(users, self.protocol)
        state = {'id': name, 'case': case['name'], 'stage': stage, 'users': users, 'shards': allocation,
                 'database': read(case_dir / 'database.json')['database'], 'session_id': case_dir.name,
                 'run_id': self.name + '-' + stage + '-' + str(users), 'search_action': action,
                 'classification': 'INCOMPLETE'}
        write(directory / 'phase.json', state)
        self.event('phase_start', case=case['name'], **{k: state[k] for k in ['id', 'stage', 'users']})
        logs, processes = [], []
        try:
            self.control('snapshot', cdir + '/before-load.json', '--case', ccase + '/app.json')
            pre = read(directory / 'before-load.json')
            assert pre.get('app_healthy') is True and pre.get('actual_app', {}).get('valid') is True, 'invalid pre-load app witness'
            app = read(case_dir / 'app.json')
            for container, label, pgid in [(self.target, 'target', app['pgid']), (self.client, 'load', -1)]:
                self.docker('exec', '--user', 'root', '-d', container, 'python3', self.monitor_helper,
                            '--out', cdir + '/' + label + '-monitor.jsonl', '--stop', cdir + '/' + label + '-monitor.stop', '--app-pgid', str(pgid))
            start_ms = time.time_ns() // 1000000 + 5000
            durations = self.protocol[stage]
            commands = []
            for shard in allocation:
                i = shard['box_index']
                argv = ['docker', 'exec', '--user', 'root', '--env', 'GOMAXPROCS=2', self.client, self.cfg['native_binary'], 'run',
                        '-target', f"http://{shard['host']}:{self.cfg['port']}", '-users', str(shard['users']),
                        '-ramp', str(durations['ramp_s']) + 's', '-measure', str(durations['measure_s']) + 's',
                        '-tail', str(durations['tail_s']) + 's', '-articles', '500000', '-think-scale', '1',
                        '-box-index', str(i), '-id-offset', str(shard['id_offset']), '-start-at', str(start_ms),
                        '-run-id', state['run_id'], '-secret', self.cfg['jwt_secret'], '-out', cdir + f'/box{i}.json']
                commands.append(argv)
                log = (directory / f'box{i}.log').open('x'); logs.append(log)
                processes.append(subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT))
            self.current_generators = processes
            write(directory / 'load-commands.json', commands)
            self.client_environment_witness(directory, state['run_id'], len(allocation))
            deadline = time.monotonic() + sum(durations.values()) + 45
            heartbeat = time.monotonic() + 15
            while any(proc.poll() is None for proc in processes):
                if time.monotonic() > deadline:
                    self.kill_generators()
                    raise TimeoutError('owned native generators exceeded phase deadline')
                if time.monotonic() >= heartbeat:
                    self.event('phase_running', case=case['name'], id=name, active_shards=sum(proc.poll() is None for proc in processes))
                    heartbeat += 15
                time.sleep(1)
            state['load_exits'] = [proc.returncode for proc in processes]
            assert state['load_exits'] == [0] * len(allocation), 'native generator failed'
            merged = self.docker('exec', '--user', 'root', self.client, self.cfg['native_binary'], 'merge',
                                 '-o', cdir + '/merged.json', *[cdir + f'/box{i}.json' for i in range(len(allocation))],
                                 allowed=(0, 3), save=directory / 'merged.txt')
            state['merge_exit'] = merged.returncode
        except Exception as error:
            state['error'] = type(error).__name__ + ': ' + str(error)
            self.kill_generators()
        except BaseException as error:
            state['error'] = type(error).__name__ + ': ' + str(error)
            self.kill_generators()
            raise
        finally:
            for log in logs:
                log.close()
            for label in ['target', 'load']:
                (directory / (label + '-monitor.stop')).touch()
            time.sleep(1.2)
            try:
                self.control('snapshot', cdir + '/after-load.json', '--case', ccase + '/app.json')
            except Exception as error:
                state['after_snapshot_error'] = str(error)
            write(directory / 'phase.json', state)
            result = audit_phase(directory, case_dir, self.plan, case, self.initial)
            write(directory / 'assessment.json', result)
            self.event('phase_complete', case=case['name'], id=name, classification=result['classification'],
                       native_qualified=result.get('native_qualified'), native_lg_limited=result.get('native_verdict', {}).get('lg_limited'),
                       local_qualified=result.get('local_qualified'), classification_scope=result.get('classification_scope'),
                       native_whole_vm_CPU_flag_count=result.get('native_whole_vm_CPU_flag_count'), client_cpu_scope_policy=self.cpu_scope_policy)
            self.current_generators = []
        return result

    def run_case(self, case):
        directory = self.root / 'cases' / case['name']
        directory.mkdir(parents=True, exist_ok=False)
        cdir = self.croot + '/cases/' + case['name']
        record = {'case': case['name'], 'status': 'INCOMPLETE', 'phases': []}
        self.case_records.append(record)
        self.event('case_start', case=case['name'])
        db = database_name(self.name, len(self.case_records))
        app_started = False
        clone_requested = False
        try:
            original = dict(case)
            write(directory / 'case.json', original)
            self.control('freeze', cdir + '/frozen', '--case', cdir + '/case.json')
            metadata = read(directory / 'frozen/metadata.json')
            assert metadata['binary_sha256'] == case['expected_binary_sha256'], 'binary differs from frozen plan'
            runtime = dict(case, metadata=cdir + '/frozen/metadata.json')
            write(directory / 'case.json', runtime)
            conf = case.get('conformance', {})
            if conf.get('log_host_path'):
                src = Path(conf['log_host_path'])
                assert sha(src) == conf['log_sha256'], 'conformance log changed'
                shutil.copy2(src, directory / 'conformance.log')
            clone_requested = True
            self.control('clone', cdir + '/database.json', '--database', db, timeout=240)
            self.control('snapshot', cdir + '/before-session.json')
            self.control('start', cdir + '/app.json', '--case', cdir + '/case.json', '--database', db,
                         '--port', str(self.cfg['port']), '--secret', self.cfg['jwt_secret'], timeout=80)
            app_started = True
            self.idle(5)
            while True:
                action = next_action(record['phases'], self.protocol)
                if action['stage'] == 'stop':
                    record['status'], record['stop_action'] = action['reason'], action
                    break
                if record['phases']:
                    self.idle(self.protocol['between_phase_minimum_s'])
                result = self.phase(directory, cdir, case, action, len(record['phases']) + 1)
                record['phases'].append(result)
                write(directory / 'session.json', record)
        except Exception as error:
            record.update(status='INVALID_SESSION', error=type(error).__name__ + ': ' + str(error))
        finally:
            if (directory / 'app.json').exists():
                try:
                    self.control('stop', cdir + '/stopped.json', '--case', cdir + '/app.json')
                except Exception as error:
                    record['stop_error'] = str(error)
            if clone_requested:
                try:
                    self.control('drop', cdir + '/dropped.json', '--database', db)
                except Exception as error:
                    if not (directory / 'database.json').exists() and 'does not exist' in str(error):
                        record['database_never_created'] = True
                    else:
                        record['drop_error'] = str(error)
            with contextlib.suppress(Exception):
                self.control('snapshot', cdir + '/after-session.json')
            write(directory / 'session.json', record)
            write(self.root / 'sessions.json', self.case_records)
            self.event('case_complete', case=case['name'], status=record['status'])
            if 'stop_error' in record or 'drop_error' in record:
                raise RuntimeError('owned session cleanup failed; refusing to launch another case')

    def run(self):
        failure = None
        hostthread = None
        try:
            target = self.inspect(self.target, self.root / 'target-inspect.json', 8, 16 * 1024**3)
            assert target['State']['Running']
            self.control('probe-limits', self.croot + '/runuser-prlimit-probe.json')
            self.control('snapshot', self.croot + '/target-initial.json')
            self.initial = read(self.root / 'target-initial.json')
            settings = {r['name']: r['setting'] for r in self.initial['pg_settings']}
            assert settings['server_version_num'].startswith('18') and settings['max_connections'] == '100'
            assert all(settings[k] == 'on' for k in ['fsync', 'synchronous_commit', 'full_page_writes']), 'PostgreSQL durability differs'
            low, high = map(int, self.initial['ip_local_port_range'].split())
            assert 20000 < high - low - 1024, 'too few ephemeral ports per destination'
            check = "import socket,sys;sys.exit(1 if any(socket.socket().connect_ex(('127.0.0.'+str(i),int(sys.argv[1])))==0 for i in range(1,9)) else 0)"
            self.docker('exec', '--user', 'root', self.target, 'python3', '-c', check, str(self.cfg['port']))
            self.docker('run', '-d', '--user', 'root', '--name', self.client, '--label', 'multicore.local.owner=' + self.name,
                        '--cpus', str(self.load_cpus), '--memory', str(self.load_memory), '--memory-swap', str(self.load_memory), '--ulimit', 'nofile=200000:200000',
                        '--network', 'container:' + self.target,
                        '--volume', str(self.host_base) + ':' + self.cfg['container_evidence'] + ':rw',
                        '--volume', self.cfg['old_host_evidence'] + ':/evidence:ro',
                        '--env', 'GOMAXPROCS=2',
                        '--entrypoint', '/bin/sh', self.cfg.get('load_image') or target['Image'], '-c', 'exec sleep infinity')
            self.load_created = True
            self.inspect(self.client, self.root / 'load-inspect.json', self.load_cpus, self.load_memory)
            self.docker('exec', '--user', 'root', self.client, 'sha256sum', self.cfg['native_binary'], save=self.root / 'native-sha256.txt')
            assert (self.root / 'native-sha256.txt').read_text().split()[0] == self.cfg['expected_native_sha256'], 'native generator binary differs'
            hostthread = threading.Thread(target=self.host_monitor, daemon=True); hostthread.start()
            for index, case in enumerate(self.cfg['cases']):
                self.run_case(case)
                if index + 1 < len(self.cfg['cases']):
                    self.idle(self.protocol['between_phase_minimum_s'])
        except BaseException as error:
            failure = type(error).__name__ + ': ' + str(error)
            self.event('controller_error', error=failure)
            self.kill_generators()
        finally:
            self.stop_host.set()
            if hostthread:
                hostthread.join(timeout=10)
            resource_errors = []
            if self.load_created:
                with contextlib.suppress(Exception):
                    self.docker('stop', '--time', '10', self.client)
                try:
                    self.inspect(self.client, self.root / 'load-final-inspect.json', self.load_cpus, self.load_memory)
                except Exception as error:
                    resource_errors.append(str(error))
            try:
                self.inspect(self.target, self.root / 'target-final-inspect.json', 8, 16 * 1024**3)
            except Exception as error:
                resource_errors.append(str(error))
            write(self.root / 'final-resource-check.json', {'valid': not resource_errors, 'errors': resource_errors,
                  'target_cpus': 8, 'target_memory_bytes': 16 * 1024**3,
                  'load_cpus': self.load_cpus, 'load_memory_bytes': self.load_memory})
            write(self.root / 'controller-result.json', {'error': failure, 'cases': self.case_records, 'resource_errors': resource_errors})
            self.event('controller_finished', error=failure, output=str(self.root))
            self.events.close()
        return 1 if failure or resource_errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        raise SystemExit(Controller(args.plan).run())
    if not args.config:
        parser.error('--config is required to prepare a plan')
    prepare(args.config, args.plan)


if __name__ == '__main__':
    main()
