#!/usr/bin/env python3
"""Compare actual exported read-only PREPARE queries on one unchanged database.

Run only outside performance trials. The caller supplies the real Goose SQL
exports and PG* environment. No schema/data writes or server-wide settings.
Each case is checked for exact ordered result equality, then measured with
alternating AB/BA EXPLAIN ANALYZE after untimed warmups. Raw plans are retained.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--baseline', type=Path, required=True)
p.add_argument('--candidate', type=Path, required=True)
p.add_argument('--cases', type=Path, required=True)
p.add_argument('--database', required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--repeats', type=int, default=6)
a = p.parse_args()
assert 2 <= a.repeats <= 20
assert not a.out.exists(), 'retain previous attempts; choose a new output'

def literal(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, list) and value:
        assert all(type(x) is type(value[0]) for x in value)
        cast = 'bigint[]' if isinstance(value[0], int) else 'text[]'
        return 'ARRAY[' + ','.join(literal(x) for x in value) + ']::' + cast
    raise ValueError('unsupported argument: ' + repr(value))

def exports(path, prefix):
    statements = {}
    lines = []
    for line in path.read_text().splitlines():
        match = re.fullmatch(r'PREPARE s(\d+)(\([A-Za-z0-9_\[\], ]*\))? AS (.+);', line)
        assert match, 'expected actual one-line Goose PREPARE output'
        number, types, body = match.groups()
        statements[int(number)] = body
        lines.append('PREPARE ' + prefix + number + (types or '') + ' AS ' + body + ';')
    return statements, '\n'.join(lines)

bodies, definitions = {}, []
for name, path in [('baseline', a.baseline), ('candidate', a.candidate)]:
    bodies[name], sql = exports(path, name + '_s')
    definitions.append(sql)

cases = json.loads(a.cases.read_text())
read_ids = {7,8,9,10,11,12,21,24,25,26,27,28,29,30,31,32,33,34,35}
sql = ['SET plan_cache_mode=force_generic_plan; SET jit=off; SET max_parallel_workers_per_gather=0;', *definitions]
outputs = []
for case in cases:
    assert case['statement'] in read_ids
    number = case['statement']
    args = [literal(value) for value in case['arguments']]
    aliases = ','.join('c'+str(i) for i in range(case['columns']))
    for variant in ['baseline', 'candidate']:
        body = re.sub(r'\$(\d+)', lambda m: '('+args[int(m[1])-1]+')', bodies[variant][number])
        sql.append("SELECT COALESCE(json_agg(row_to_json(q)),'[]'::json) FROM ("+body+') q('+aliases+');')
        outputs.append({'kind':'rows','case':case['id'],'variant':variant})
    call = '('+','.join(args)+')'
    for variant in ['baseline', 'candidate']:
        sql.append('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) EXECUTE '+variant+'_s'+str(number)+call+';')
        outputs.append({'kind':'warmup','case':case['id'],'variant':variant})
    for repeat in range(a.repeats):
        order = ['baseline','candidate'] if repeat%2 == 0 else ['candidate','baseline']
        for variant in order:
            sql.append('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) EXECUTE '+variant+'_s'+str(number)+call+';')
            outputs.append({'kind':'plan','case':case['id'],'variant':variant,'repeat':repeat,'order':order})

began = time.time()
a.out.parent.mkdir(parents=True, exist_ok=True)
inputs = {str(path):hashlib.sha256(path.read_bytes()).hexdigest()
          for path in [a.baseline,a.candidate,a.cases,Path(__file__)]}
a.out.write_text(json.dumps({'status':'INCOMPLETE','started_unix_s':began,
                            'inputs_sha256':inputs},indent=2)+'\n')
proc = subprocess.run(['psql','-X','-A','-t','-q','-v','ON_ERROR_STOP=1','-d',a.database],
                      input='\n'.join(sql)+'\n', text=True, capture_output=True, timeout=240)
a.out.with_suffix('.stdout.txt').write_text(proc.stdout)
a.out.with_suffix('.stderr.txt').write_text(proc.stderr)
if proc.returncode:
    a.out.write_text(json.dumps({'status':'FAILED_QUERY','started_unix_s':began,
                                'finished_unix_s':time.time(),'inputs_sha256':inputs,
                                'psql_exit':proc.returncode,'error':proc.stderr},indent=2)+'\n')
    raise SystemExit(proc.returncode)
decoder, text = json.JSONDecoder(), proc.stdout.strip()
results = []
for label in outputs:
    value, end = decoder.raw_decode(text)
    text = text[end:].lstrip()
    results.append(dict(label, result=value))
assert not text
summary = []
for case in cases:
    selected = [r for r in results if r['case'] == case['id']]
    rows = {r['variant']:r['result'] for r in selected if r['kind']=='rows'}
    equal = rows['baseline'] == rows['candidate']
    timing = {v:[r['result'][0]['Execution Time'] for r in selected if r['kind']=='plan' and r['variant']==v]
              for v in ['baseline','candidate']}
    summary.append({'case':case['id'],'ordered_rows_equal':equal,'row_count':len(rows['baseline']),
                    'execution_ms':timing,'median_ms':{v:statistics.median(x) for v,x in timing.items()}})
record = {'database':a.database,'started_unix_s':began,'finished_unix_s':time.time(),
          'scope':'Read-only query-plan diagnostic, not a workload/capacity benchmark',
          'all_ordered_results_equal':all(r['ordered_rows_equal'] for r in summary),
          'inputs_sha256':inputs,
          'summary':summary,'results':results,'psql_exit':proc.returncode}
a.out.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'saved':str(a.out),'all_ordered_results_equal':record['all_ordered_results_equal'],'cases':len(cases)}))
raise SystemExit(0 if record['all_ordered_results_equal'] else 1)
