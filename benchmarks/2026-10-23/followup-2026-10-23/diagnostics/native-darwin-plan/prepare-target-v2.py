#!/usr/bin/env python3
"""Prepare a distinct loopback target from a stopped, preserved checkpoint.

Runtime preparation only when explicitly scheduled. This script starts no app
or load, builds nothing, never removes a container/image/data, and changes no
host settings. A failed attempt retains its receipts and any stopped new target.
"""
import argparse
import contextlib
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import signal
import socket
import subprocess
import time
import traceback
import uuid


HERE = Path(__file__).resolve().parent
HOST_COMPARISON = Path('/private/tmp/multicore-comparison-20261023').resolve()
OLD = 'multicore-comparison-target-20261023'
V1 = HERE / 'prepare-target.py'
FAILED_V1 = HERE / 'target-preparation-20261023' / 'operations.json'
HELPER = '/evidence/lab-target-control-v2.py'
CPUS, MEMORY = 8, 16 * 1024**3
PORTS = list(range(33000, 33016))
OWNER_LABEL = 'multicore.local.native_preparation_owner'
CHARGING_SAMPLES, CHARGING_INTERVAL_SECONDS = 6, 10


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def power_state(text):
    """Accept explicit charging/charged battery states on AC, never a substring."""
    lines = text.splitlines()
    ac = any(line.strip() == "Now drawing from 'AC Power'" for line in lines)
    states = []
    for line in lines:
        if 'InternalBattery-' not in line:
            continue
        fields = line.split(';')
        state = fields[1].strip().lower() if len(fields) > 1 else ''
        states.append(state)
    return {'safe': ac and bool(states) and all(state in ('charging', 'charged') for state in states),
            'ac_power': ac, 'battery_states': states}


def resource_budget(inspect):
    h = inspect['HostConfig']
    return (h.get('NanoCpus') == CPUS * 10**9 and h.get('Memory') == MEMORY
            and h.get('MemorySwap') == MEMORY and h.get('CpusetCpus', '') == ''
            and h.get('CpusetMems', '') == '')


def snapshot_budget(snapshot):
    value = snapshot.get('cpu.max', '')
    fields = value.split() if isinstance(value, str) else []
    ratio = (len(fields) == 2 and all(re.fullmatch(r'[0-9]+', field) for field in fields)
             and int(fields[0]) > 0 and int(fields[1]) > 0
             and int(fields[0]) == CPUS * int(fields[1]))
    return (ratio and str(snapshot.get('memory.max')) == str(MEMORY)
            and str(snapshot.get('memory.swap.max')) == '0')


def mount_identity(mounts):
    return sorted((m['Type'], m['Source'], m['Destination'], bool(m['RW']),
                   m.get('Propagation', 'rprivate')) for m in mounts)


def json_write(path, data):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


class Preparation:
    def __init__(self, args):
        requested = args.out.absolute()
        if requested.exists() or requested.is_symlink():
            raise FileExistsError('refusing existing output: ' + str(requested))
        self.out = requested.resolve()
        relative = self.out.relative_to(HOST_COMPARISON)
        if (FAILED_V1.parent == self.out or FAILED_V1.parent in self.out.parents):
            raise ValueError('new output must be separate from the preserved failed V1 attempt')
        self.container_out = str(PurePosixPath('/comparison') / relative.as_posix())
        self.token = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dt%H%M%S') + '-' + uuid.uuid4().hex[:8]
        self.new = args.new_target or ('multicore-native-target-' + self.token)
        self.image_tag = args.image or ('multicore-native-checkpoint:' + self.token)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', self.new) or self.new == OLD:
            raise ValueError('invalid or original --new-target name')
        if not re.fullmatch(r'[a-z0-9][a-z0-9._/-]*:[a-z0-9][a-z0-9._-]*', self.image_tag):
            raise ValueError('--image must be an explicit lower-case repository:tag')
        self.preserved_before = {str(path): sha(path) for path in [V1, FAILED_V1]}
        self.script_hash = sha(Path(__file__).resolve())
        self.out.mkdir(parents=True, exist_ok=False)
        self.operations = []
        self.old_id = self.new_id = self.image_id = None
        self.old_start_attempted = self.new_create_attempted = False
        self.old_stopped = False
        self.original = self.new_inspect = None
        self.error = None
        self.cleanup_errors = []
        self.record('preparation_created', output=str(self.out), container_output=self.container_out,
                    new_target=self.new, image_tag=self.image_tag, ownership_token=self.token,
                    original_preservation_sha256=self.preserved_before, preparer_sha256=self.script_hash)
        json_write(self.out / 'preservation-before.json', self.preserved_before)

    def record(self, kind, **fields):
        self.operations.append({'event': kind, 'utc': utc(), 'monotonic_ns': time.monotonic_ns(), **fields})
        json_write(self.out / 'operations.json', self.operations)

    def require(self, condition, description):
        self.record('validation', description=description, passed=bool(condition))
        if not condition:
            raise RuntimeError(description)

    def run(self, argv, *, allowed=(0,), timeout=120):
        entry = {'event': 'command', 'argv': argv, 'start_utc': utc(),
                 'start_wall_ns': time.time_ns(), 'start_monotonic_ns': time.monotonic_ns(),
                 'pending': True, 'exit': None}
        self.operations.append(entry)
        json_write(self.out / 'operations.json', self.operations)
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            entry.update(exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except BaseException as error:
            def text(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else (value or '')
            entry.update(exit=None, error_type=type(error).__name__, error=str(error),
                         stdout=text(getattr(error, 'stdout', '')), stderr=text(getattr(error, 'stderr', '')))
            raise
        finally:
            entry.update(end_wall_ns=time.time_ns(), end_monotonic_ns=time.monotonic_ns(), end_utc=utc(), pending=False)
            json_write(self.out / 'operations.json', self.operations)
        if result.returncode not in allowed:
            raise RuntimeError('command failed: ' + repr(argv) + ': ' + result.stderr)
        return result

    def inspect(self, name):
        rows = json.loads(self.run(['docker', 'container', 'inspect', name]).stdout)
        self.require(len(rows) == 1, 'exactly one container inspection: ' + name)
        return rows[0]

    def absent(self, kind, name):
        result = self.run(['docker', kind, 'inspect', name], allowed=(0, 1))
        if result.returncode == 0:
            raise FileExistsError('refusing existing ' + kind + ': ' + name)
        self.require(re.search(r'no such (?:image|container|object)', result.stderr, re.I) is not None,
                     'absence response is explicit, not a Docker service failure: ' + name)

    def power(self, phase):
        result = self.run(['pmset', '-g', 'batt'], timeout=10)
        state = power_state(result.stdout)
        self.record('charging_check', phase=phase, **state)
        self.require(state['safe'], 'AC with explicit charging/charged battery state: ' + phase)

    def stable_charging(self):
        started = time.monotonic_ns()
        for index in range(CHARGING_SAMPLES):
            self.power('stable-preflight-' + str(index + 1))
            if index + 1 < CHARGING_SAMPLES:
                self.record('charging_settle_wait', seconds=CHARGING_INTERVAL_SECONDS)
                time.sleep(CHARGING_INTERVAL_SECONDS)
        self.record('stable_charging_preflight_passed', samples=CHARGING_SAMPLES,
                    elapsed_seconds=(time.monotonic_ns() - started) / 1e9)

    def pg_status(self, container):
        return self.run(['docker', 'exec', '--user', 'root', container,
                         'pg_ctlcluster', '18', 'main', 'status'], allowed=(0, 3)).returncode

    def start_pg(self, container, phase):
        if self.pg_status(container) == 3:
            self.power(phase)
            self.run(['docker', 'exec', '--user', 'root', container, 'pg_ctlcluster', '18', 'main', 'start'])
        for attempt in range(20):
            ready = self.run(['docker', 'exec', '--user', 'root', container, 'pg_isready'], allowed=(0, 1, 2), timeout=10)
            if ready.returncode == 0:
                return
            time.sleep(.5)
        raise RuntimeError('PostgreSQL18 did not become ready: ' + phase)

    def stop_pg(self, container):
        if self.pg_status(container) == 0:
            self.run(['docker', 'exec', '--user', 'root', container,
                      'pg_ctlcluster', '18', 'main', 'stop', '--mode', 'fast'])
        self.require(self.pg_status(container) == 3, 'PostgreSQL18 stopped before checkpoint/target stop')

    def snapshot(self, container, name):
        self.run(['docker', 'exec', '--user', 'root', container, 'python3', HELPER,
                  'snapshot', '--out', self.container_out + '/' + name])
        snapshot = json.loads((self.out / name).read_text())
        self.require(snapshot_budget(snapshot), name + ': actual8CPU/16GiB/no-swap budget')
        settings = {row['name']: row['setting'] for row in snapshot['pg_settings']}
        self.require(str(settings.get('server_version_num', '')).startswith('18'), name + ': PostgreSQL18')
        self.require(settings.get('max_connections') == '100' and all(settings.get(key) == 'on' for key in
                     ['fsync', 'synchronous_commit', 'full_page_writes']), name + ': original durable PG conditions')
        return snapshot

    def prepare(self):
        self.stable_charging()  # no Docker or socket operation before stable charging
        self.absent('container', self.new)
        self.absent('image', self.image_tag)
        self.original = self.inspect(OLD)
        self.old_id = self.original['Id']
        self.require(self.original['State']['Running'] is False, 'original target is initially stopped; no active run may be interrupted')
        self.old_stopped = True
        self.require(resource_budget(self.original), 'original Docker8CPU/16GiB/no-swap/no-affinity budget')
        mounts = self.original['Mounts']
        self.require(all(m['Type'] == 'bind' for m in mounts), 'all original mounts are bind mounts')
        self.require(any(Path(m['Source']).resolve() == HOST_COMPARISON and m['Destination'] == '/comparison'
                         and m['RW'] for m in mounts), 'host output maps through the actual writable /comparison bind')
        self.require(all(not any(char in m['Source'] + m['Destination'] for char in ',\x00\n') for m in mounts),
                     'mount paths can be represented without ambiguous --mount CSV')
        json_write(self.out / 'original-inspect.json', self.original)
        with contextlib.ExitStack() as stack:
            for port in PORTS:
                sock = stack.enter_context(socket.socket())
                sock.bind(('127.0.0.1', port))
        self.record('loopback_ports_available', ports=PORTS)
        self.power('before-original-start')
        self.old_start_attempted = True
        self.old_stopped = False
        self.run(['docker', 'start', self.old_id])
        self.start_pg(self.old_id, 'before-original-PG-start')
        before = self.snapshot(self.old_id, 'old-before.json')
        data_directory = next(row['setting'] for row in before['pg_settings'] if row['name'] == 'data_directory')
        pgdata = PurePosixPath(data_directory)
        self.require(pgdata.is_absolute() and all(
            PurePosixPath(m['Destination']) != pgdata and PurePosixPath(m['Destination']) not in pgdata.parents
            and pgdata not in PurePosixPath(m['Destination']).parents for m in mounts),
            'PG data is in the checkpoint writable layer, not a shared bind mount')
        self.stop_pg(self.old_id)
        self.run(['docker', 'stop', '--timeout', '10', self.old_id])
        stopped = self.inspect(self.old_id)
        self.old_stopped = stopped['State']['Running'] is False
        self.require(self.old_stopped, 'original target stopped before Docker commit')
        json_write(self.out / 'original-stopped-before-commit.json', stopped)
        self.power('before-checkpoint-commit')
        self.absent('image', self.image_tag)
        image = self.run(['docker', 'commit', '--change', 'LABEL ' + OWNER_LABEL + '=' + self.token,
                          self.old_id, self.image_tag], timeout=300).stdout.strip()
        self.require(re.fullmatch(r'sha256:[0-9a-f]{64}', image) is not None, 'commit returned an immutable image ID')
        self.image_id = image
        image_inspect = json.loads(self.run(['docker', 'image', 'inspect', self.image_tag]).stdout)[0]
        self.require(image_inspect['Id'] == image and image_inspect['Config']['Labels'].get(OWNER_LABEL) == self.token,
                     'new image ID and ownership label match this preparation')
        json_write(self.out / 'image-inspect.json', image_inspect)
        self.power('before-new-target-create')
        self.absent('container', self.new)
        argv = ['docker', 'create', '--pull=never', '--name', self.new, '--label', OWNER_LABEL + '=' + self.token,
                '--cpus', str(CPUS), '--memory', str(MEMORY), '--memory-swap', str(MEMORY),
                '--ulimit', 'nofile=200000:200000']
        for port in PORTS:
            argv += ['--publish', '127.0.0.1:' + str(port) + ':3000']
        for mount in mounts:
            spec = 'type=bind,src=' + mount['Source'] + ',dst=' + mount['Destination']
            spec += ',bind-propagation=' + mount.get('Propagation', 'rprivate')
            if not mount['RW']:
                spec += ',readonly'
            argv += ['--mount', spec]
        argv += ['--entrypoint', '/bin/sh', self.image_id, '-c', 'exec sleep infinity']
        self.new_create_attempted = True
        self.new_id = self.run(argv).stdout.strip()
        self.require(re.fullmatch(r'[0-9a-f]{64}', self.new_id) is not None, 'create returned the new container ID')
        self.power('before-new-target-start')
        self.run(['docker', 'start', self.new_id])
        self.new_inspect = self.inspect(self.new_id)
        new = self.new_inspect
        self.require(new['Config']['Labels'].get(OWNER_LABEL) == self.token and new['Image'] == self.image_id,
                     'new target uses this preparation ownership and immutable checkpoint image')
        self.require(resource_budget(new), 'new Docker8CPU/16GiB/no-swap/no-affinity budget')
        self.require(mount_identity(new['Mounts']) == mount_identity(mounts), 'new target has the same exact bind mounts')
        bindings = new['HostConfig'].get('PortBindings', {})
        actual_ports = {(m['HostIp'], int(m['HostPort'])) for m in bindings.get('3000/tcp', [])}
        self.require(set(bindings) == {'3000/tcp'} and actual_ports == {('127.0.0.1', port) for port in PORTS},
                     'only the sixteen requested loopback3000 mappings are published')
        json_write(self.out / 'new-inspect.json', new)
        self.start_pg(self.new_id, 'before-new-PG-start')
        after = self.snapshot(self.new_id, 'new-after.json')
        self.require(before['pg_settings'] == after['pg_settings'], 'all original PostgreSQL settings and sources are equal')
        self.require(before['official_source_sha256'] == after['official_source_sha256'], 'all official source hashes are equal')
        self.power('preparation-complete')

    def cleanup_new(self):
        if not self.new_create_attempted:
            return
        result = self.run(['docker', 'container', 'inspect', self.new], allowed=(0, 1))
        if result.returncode == 1:
            self.require(re.search(r'no such (?:container|object)', result.stderr, re.I) is not None,
                         'failed new create left no container')
            return
        new = json.loads(result.stdout)[0]
        self.require(new['Config']['Labels'].get(OWNER_LABEL) == self.token and
                     (self.new_id is None or new['Id'] == self.new_id), 'cleanup may stop only this preparation new target')
        self.new_id = new['Id']
        if new['State']['Running']:
            try:
                self.stop_pg(self.new_id)
            except BaseException as error:
                self.record('cleanup_pg_error', target='new', error_type=type(error).__name__, error=str(error))
            self.run(['docker', 'stop', '--timeout', '10', self.new_id])
        self.require(self.inspect(self.new_id)['State']['Running'] is False, 'failed new target retained stopped')

    def cleanup_original(self):
        if self.old_id is None:
            return
        current = self.inspect(self.old_id)
        if current['State']['Running']:
            self.require(self.old_start_attempted, 'cleanup does not interrupt an original target it did not start')
            try:
                self.stop_pg(self.old_id)
            except BaseException as error:
                self.record('cleanup_pg_error', target='original', error_type=type(error).__name__, error=str(error))
            self.run(['docker', 'stop', '--timeout', '10', self.old_id])
            current = self.inspect(self.old_id)
        self.old_stopped = current['State']['Running'] is False
        self.require(self.old_stopped, 'original target is preserved stopped at end')
        json_write(self.out / 'original-final-inspect.json', current)

    def execute(self):
        try:
            self.prepare()
            self.require({str(p): sha(p) for p in [V1, FAILED_V1]} == self.preserved_before,
                         'V1 and original failed receipt are byte-for-byte unchanged')
        except BaseException as error:
            self.error = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
            self.record('preparation_error', **self.error)
        try:
            self.cleanup_original()
        except BaseException as error:
            self.cleanup_errors.append({'target': 'original', 'type': type(error).__name__, 'message': str(error)})
            self.record('cleanup_error', **self.cleanup_errors[-1])
        preserved_after = {}
        try:
            preserved_after = {str(path): sha(path) for path in [V1, FAILED_V1]}
            json_write(self.out / 'preservation-after.json', preserved_after)
        except BaseException as error:
            self.cleanup_errors.append({'target': 'preservation', 'type': type(error).__name__, 'message': str(error)})
            self.record('cleanup_error', **self.cleanup_errors[-1])
        preservation_ok = preserved_after == self.preserved_before
        # A failure discovered during final preservation/stop verification is
        # still a failed preparation: do not leave the newly owned target live.
        if self.error or self.cleanup_errors or not self.old_stopped or not preservation_ok:
            try:
                self.cleanup_new()
            except BaseException as error:
                self.cleanup_errors.append({'target': 'new', 'type': type(error).__name__, 'message': str(error)})
                self.record('cleanup_error', **self.cleanup_errors[-1])
        success = self.error is None and not self.cleanup_errors and self.old_stopped and preservation_ok
        proof = {'schema': 'native-darwin-target-preparation-v2',
                 'status': 'PREPARED_NOT_BENCHMARKED' if success else 'FAILED_PRESERVED_ATTEMPT',
                 'created_utc': utc(), 'old_target': OLD, 'old_container_id': self.old_id,
                 'old_preserved_stopped': self.old_stopped, 'old_start_attempted': self.old_start_attempted,
                 'new_target': self.new, 'new_container_id': self.new_id,
                 'image': self.image_id, 'image_tag': self.image_tag,
                 'ownership_token': self.token, 'host_output_dir': str(self.out),
                 'container_output_dir': self.container_out, 'loopback_ports': PORTS,
                 'server_cpus': CPUS, 'server_memory_bytes': MEMORY,
                 'server_budget_matches': success, 'no_swap': success, 'no_affinity': success,
                 'original_pg_settings_equal': success, 'original_sources_equal': success,
                 'host_settings_changed': False, 'build_or_app_or_load_started': False,
                 'original_v1_and_failed_receipt_unchanged': preservation_ok,
                 'preservation_before_sha256': self.preserved_before,
                 'preservation_after_sha256': preserved_after, 'preparer_sha256': self.script_hash,
                 'charging_preflight_samples': CHARGING_SAMPLES,
                 'charging_preflight_interval_seconds': CHARGING_INTERVAL_SECONDS,
                 'error': self.error, 'cleanup_errors': self.cleanup_errors,
                 'failure_retention': 'No image, container, data, or prior receipt is removed. Failed owned targets are stopped when reachable. An uninspected original is never started or stopped.',
                 'scope': 'Target preparation only; no capacity, performance, or ranking claim'}
        json_write(self.out / 'proof.json', proof)
        print(json.dumps(proof), flush=True)
        return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='new unique output directory under the /comparison host bind')
    parser.add_argument('--new-target', help='new unused container name; default is unique')
    parser.add_argument('--image', help='new unused repository:tag; default is unique')
    args = parser.parse_args()
    def interrupted(signum, _frame):
        raise KeyboardInterrupt('preparation interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    return Preparation(args).execute()


if __name__ == '__main__':
    raise SystemExit(main())
