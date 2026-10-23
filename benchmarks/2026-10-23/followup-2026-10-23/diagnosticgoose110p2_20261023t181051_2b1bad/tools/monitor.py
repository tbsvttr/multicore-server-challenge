#!/usr/bin/env python3
"""Read-only 1Hz cgroup/process witness, run inside one owned container."""
import argparse
import json
import os
import pathlib
import time

p = argparse.ArgumentParser()
p.add_argument('--out', required=True)
p.add_argument('--stop', required=True)
p.add_argument('--app-pgid', type=int, default=-1)
a = p.parse_args()
cg = pathlib.Path('/sys/fs/cgroup')
hz, pagesize = os.sysconf('SC_CLK_TCK'), os.sysconf('SC_PAGE_SIZE')

def read(path):
    try:
        return pathlib.Path(path).read_text().strip()
    except (OSError, ValueError):
        return None

with open(a.out, 'x') as out:
    while not pathlib.Path(a.stop).exists():
        at = time.monotonic()
        row = {'wall_ns': time.time_ns(), 'monotonic_ns': time.monotonic_ns(),
               'cpu': {}, 'pg': {'cpu_s': 0, 'rss_bytes': 0, 'pids': []},
               'app': {'cpu_s': 0, 'rss_bytes': 0, 'pids': []}}
        for line in (read(cg/'cpu.stat') or '').splitlines():
            k, v = line.split()
            row['cpu'][k] = int(v)
        for name in ['memory.current', 'memory.peak', 'memory.max', 'memory.swap.current',
                     'memory.swap.max', 'memory.events', 'cpu.max', 'cpu.pressure', 'memory.pressure']:
            row[name] = read(cg/name)
        for path in pathlib.Path('/proc').glob('[0-9]*/stat'):
            try:
                txt = path.read_text()
                comm = txt[txt.index('(')+1:txt.rindex(')')]
                parts = txt[txt.rindex(')')+2:].split()
                group = int(parts[2])
                kind = 'pg' if comm == 'postgres' else 'app' if group == a.app_pgid else None
                if kind:
                    row[kind]['cpu_s'] += (int(parts[11]) + int(parts[12])) / hz
                    row[kind]['rss_bytes'] += int(parts[21]) * pagesize
                    row[kind]['pids'].append(int(path.parent.name))
            except (OSError, ValueError, IndexError):
                pass
        out.write(json.dumps(row, separators=(',', ':'))+'\n')
        out.flush()
        time.sleep(max(0.05, 1 - (time.monotonic()-at)))
