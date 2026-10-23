#!/usr/bin/env python3
"""Bounded read-only PostgreSQL observer for a separately labelled diagnosis.

Each sample opens one short psql connection. Application SQL text and parameters
are never emitted: activity records contain a query hash and heuristic family.
OUT.owner.json and OUT.done.json mean the complete --out path plus that suffix.
Run with --peer-postgres as container root when Unix peer auth requires postgres.
"""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid


QUERY = r"""
WITH stamp AS MATERIALIZED (SELECT clock_timestamp() AS ts),
app AS MATERIALIZED (
    SELECT pid, backend_type, state, wait_event_type, wait_event,
           query_start, xact_start, query
    FROM pg_stat_activity
    WHERE datname = current_database()
      AND usename = 'conduit'
      AND backend_type = 'client backend'
      AND pid <> pg_backend_pid()
      AND application_name IS DISTINCT FROM current_setting('application_name')
)
SELECT jsonb_build_object(
    'database', current_database(),
    'server_version_num', current_setting('server_version_num'),
    'server_time', (SELECT ts FROM stamp),
    'observer_backend_pid', pg_backend_pid(),
    'observer_application_name', current_setting('application_name'),
    'application_connections', (SELECT count(*) FROM app),
    'activity', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
            'pid', pid,
            'backend_type', backend_type,
            'state', state,
            'wait_event_type', wait_event_type,
            'wait_event', wait_event,
            'query_age_s', CASE WHEN query_start IS NULL THEN NULL ELSE
                EXTRACT(EPOCH FROM ((SELECT ts FROM stamp) - query_start)) END,
            'xact_age_s', CASE WHEN xact_start IS NULL THEN NULL ELSE
                EXTRACT(EPOCH FROM ((SELECT ts FROM stamp) - xact_start)) END,
            'blocking_pids', pg_blocking_pids(pid),
            'query_md5', md5(COALESCE(query, '')),
            'family', CASE
                WHEN state <> 'active' THEN 'idle'
                WHEN query ILIKE '%viewers AS MATERIALIZED%' THEN 'batch_comments'
                WHEN query ILIKE '%queries AS MATERIALIZED (SELECT DISTINCT p1,p2,p3,p4%'
                    THEN 'shared_feed'
                WHEN query ILIKE '%queries AS MATERIALIZED%' THEN 'shared_list'
                WHEN query ILIKE '%unnest($1::bigint[], $2::text[])%'
                    THEN 'batch_article'
                WHEN query ILIKE '%unnest(%' THEN 'batch_other'
                WHEN query ILIKE '%password_hash FROM users%' THEN 'login_read'
                WHEN query ILIKE '%INSERT INTO%' OR query ILIKE '%UPDATE users%'
                  OR query ILIKE '%UPDATE articles%' OR query ILIKE '%DELETE FROM%'
                    THEN 'write'
                WHEN query ILIKE '%FROM tags%' THEN 'tags_or_tagged_read'
                WHEN query ILIKE '%FROM comments%' THEN 'comments_read'
                WHEN query ILIKE '%FROM articles%' THEN 'article_or_list_read'
                WHEN query ILIKE '%FROM users%' THEN 'user_or_profile_read'
                ELSE 'other'
            END
        ) ORDER BY pid) FROM app
    ), '[]'::jsonb),
    'pg_stat_database', (
        SELECT to_jsonb(d) FROM pg_stat_database d
        WHERE d.datname = current_database()
    ),
    'pg_stat_checkpointer', (SELECT to_jsonb(c) FROM pg_stat_checkpointer c)
);
"""


def write_exclusive(path, obj):
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, allow_nan=False)
        f.write('\n')


def start_ticks():
    try:
        stat = Path('/proc/self/stat').read_text()
        return int(stat[stat.rindex(')') + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def run_sample(command, env, budget):
    """Kill only this freshly created observer process group on timeout."""
    child = subprocess.Popen(command, env=env, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, start_new_session=True)
    identity = {'pid': child.pid, 'pgid': child.pid}
    try:
        stdout, stderr = child.communicate(timeout=budget)
        return child.returncode, stdout, stderr, False, identity
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = child.communicate(timeout=.25)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = child.communicate(timeout=.75)
        return child.returncode, stdout, stderr, True, identity
    finally:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=.75)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--stop', type=Path)
    parser.add_argument('--database', required=True)
    parser.add_argument('--max-seconds', type=float, default=720)
    parser.add_argument('--interval', type=float, default=1)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--peer-postgres', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'mc_pair_[a-z0-9_]{1,55}', args.database):
        parser.error('--database must be an owned mc_pair_* name of at most63 characters')
    if not 1 <= args.max_seconds <= 1800:
        parser.error('--max-seconds must be between1 and1800')
    if args.interval != 1:
        parser.error('this collector has a fixed1-second interval')
    if not args.once and args.stop is None:
        parser.error('--stop is required unless --once is used')
    if args.peer_postgres and os.geteuid() != 0:
        parser.error('--peer-postgres requires root for the fixed runuser prefix')

    out = args.out.resolve()
    owner_path = Path(str(out) + '.owner.json')
    done_path = Path(str(out) + '.done.json')
    if any(path.exists() for path in [out, owner_path, done_path]):
        parser.error('refusing to overwrite output or ownership/completion receipt')
    if args.stop is not None and args.stop.exists():
        parser.error('stop file already exists before collection')
    out.parent.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    received_signal = []

    def request_stop(signum, _frame):
        received_signal.append(signum)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    pid = os.getpid()
    observer = 'mc_diag_' + str(pid) + '_' + uuid.uuid4().hex[:12]
    started_ns, started_mono_ns = time.time_ns(), time.monotonic_ns()
    owner = {
        'schema': 'mc-pg-diagnostic-owner-v1', 'pid': pid,
        'pgid': os.getpgid(0), 'uid': os.getuid(), 'start_ticks': start_ticks(),
        'observer_application_name': observer, 'database': args.database,
        'out': str(out), 'stop': str(args.stop) if args.stop else None,
        'started_wall_ns': started_ns, 'started_monotonic_ns': started_mono_ns,
        'max_seconds': args.max_seconds, 'interval_s': 1, 'once': args.once,
        'peer_postgres': args.peer_postgres,
        'observer_subprocess_policy': 'Each short psql has a fresh owned process group; timeout uses bounded TERM then KILL.',
        'observer_stats_effect': 'Each sample adds its own connection/transaction to database-wide counters; activity excludes that observer.',
        'family_label_kind': 'Heuristic SQL shape only; query_md5 preserves exact grouping without SQL text.',
        'scope': 'Read-only diagnostic observer; no capacity qualification.'
    }
    command = ['psql', '-X', '-A', '-t', '-q', '-v', 'ON_ERROR_STOP=1',
               '-d', args.database, '-c', QUERY]
    if args.peer_postgres:
        command = ['runuser', '-u', 'postgres', '--'] + command
    env = os.environ.copy()
    env.update(PGAPPNAME=observer, PGCONNECT_TIMEOUT='2')
    # runuser may reset environment on some systems; pass only these fixed
    # observer options explicitly after switching users, with no credentials.
    if args.peer_postgres:
        env.update(PGHOST='/var/run/postgresql', PGPORT='5432', PGUSER='postgres')
        command = ['runuser', '-u', 'postgres', '--', 'env',
                   'PGAPPNAME=' + observer, 'PGCONNECT_TIMEOUT=2',
                   'PGHOST=/var/run/postgresql', 'PGPORT=5432',
                   'PGUSER=postgres'] + command[4:]

    count = errors = consecutive_errors = 0
    reason = 'max_seconds'
    exception = None
    deadline = time.monotonic() + args.max_seconds
    next_sample = time.monotonic()
    backend_pids = set()
    write_exclusive(owner_path, owner)
    try:
        with out.open('x', encoding='utf-8') as stream:
            while time.monotonic() < deadline:
                if stop.is_set():
                    reason = 'signal'
                    break
                if args.stop is not None and args.stop.exists():
                    reason = 'stop_file'
                    break
                row = {'sample': count, 'wall_ns': time.time_ns(),
                       'monotonic_ns': time.monotonic_ns()}
                budget = min(3.0, deadline - time.monotonic())
                if budget <= 0:
                    break
                try:
                    code, stdout, stderr, timed_out, identity = run_sample(command, env, budget)
                    row['psql_process'] = identity
                    if timed_out:
                        row.update(ok=False, error='psql_timeout', timeout_s=budget)
                    elif code:
                        row.update(ok=False, error='psql_exit', exit=code,
                                   stderr=stderr.strip()[:600])
                    else:
                        data = json.loads(stdout)
                        if not isinstance(data, dict) or data.get('database') != args.database:
                            raise ValueError('observer connected to an unexpected database')
                        if not str(data.get('server_version_num', '')).startswith('18'):
                            raise ValueError('observer server is not PostgreSQL18')
                        if data.get('observer_application_name') != observer:
                            raise ValueError('observer application name was not preserved')
                        row.update(ok=True, postgres=data)
                        backend_pids.add(data['observer_backend_pid'])
                except subprocess.TimeoutExpired:
                    row.update(ok=False, error='psql_timeout', timeout_s=budget)
                except (OSError, ValueError, TypeError) as error:
                    row.update(ok=False, error=type(error).__name__, detail=str(error)[:600])
                row['finished_wall_ns'] = time.time_ns()
                row['finished_monotonic_ns'] = time.monotonic_ns()
                stream.write(json.dumps(row, allow_nan=False, separators=(',', ':')) + '\n')
                stream.flush()
                count += 1
                if not row['ok']:
                    errors += 1
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0
                if args.once:
                    reason = 'once'
                    break
                if consecutive_errors >= 5:
                    reason = 'five_consecutive_sample_errors'
                    break
                next_sample += 1
                # Do not run catch-up bursts after a delayed/timeout sample.
                next_sample = max(next_sample, time.monotonic())
                stop.wait(min(max(0, next_sample - time.monotonic()),
                              max(0, deadline - time.monotonic())))
    except BaseException as error:
        reason = 'exception'
        exception = type(error).__name__ + ': ' + str(error)
    finally:
        receipt = {
            'schema': 'mc-pg-diagnostic-completed-v1', 'pid': pid,
            'start_ticks': owner['start_ticks'], 'database': args.database,
            'out': str(out), 'owner_receipt': str(owner_path),
            'observer_application_name': observer,
            'observer_backend_pids': sorted(backend_pids),
            'completed': True, 'reason': reason, 'signals': received_signal,
            'samples': count, 'sample_errors': errors,
            'pass': count > 0 and errors == 0 and exception is None,
            'exception': exception, 'finished_wall_ns': time.time_ns(),
            'finished_monotonic_ns': time.monotonic_ns(),
            'elapsed_s': (time.monotonic_ns() - started_mono_ns) / 1e9,
            'scope': 'Read-only diagnostic collection; never a capacity score.'
        }
        write_exclusive(done_path, receipt)
    return 0 if receipt['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
