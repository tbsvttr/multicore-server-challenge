#!/usr/bin/env python3
"""Read-only diagnostics for one owned benchmark database, never a scored run."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--database', required=True)
p.add_argument('--out', required=True)
p.add_argument('--seconds', type=int, default=100)
a = p.parse_args()
assert re.fullmatch(r'mc_pair_[a-z0-9_]{1,52}', a.database)
sql = """SELECT json_build_object(
 'backends', COALESCE((SELECT json_agg(json_build_object(
  'pid',pid,'state',state,'wait_type',wait_event_type,'wait_event',wait_event,
  'query',left(query,2500),'query_ms',EXTRACT(epoch FROM (clock_timestamp()-query_start))*1000))
  FROM pg_stat_activity WHERE datname='%s' AND backend_type='client backend'),'[]'::json),
 'database',(SELECT row_to_json(s) FROM (SELECT xact_commit,xact_rollback,blks_read,blks_hit,
  tup_returned,tup_fetched,tup_inserted,tup_updated,tup_deleted,conflicts,temp_files,temp_bytes,
  deadlocks,blk_read_time,blk_write_time,session_time,active_time
  FROM pg_stat_database WHERE datname='%s') s))""" % (a.database, a.database)
with Path(a.out).open('x') as f:
    end = time.monotonic() + a.seconds
    i = 0
    while time.monotonic() < end:
        start = time.monotonic()
        proc = subprocess.run(['runuser','-u','postgres','--','psql','-X','-At','-d','postgres','-c',sql],
                              text=True,capture_output=True,timeout=5)
        row = {'wall_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),'exit_code':proc.returncode}
        try:
            row['sample'] = json.loads(proc.stdout)
        except ValueError:
            row['error'] = proc.stderr
        f.write(json.dumps(row)+'\n')
        f.flush()
        i += 1
        if i % 30 == 0:
            print(json.dumps({'pg_samples':i}),flush=True)
        time.sleep(max(0.01,1-(time.monotonic()-start)))
print(json.dumps({'saved':a.out,'samples':i}),flush=True)
