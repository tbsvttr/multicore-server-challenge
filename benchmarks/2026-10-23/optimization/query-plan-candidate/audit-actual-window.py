#!/usr/bin/env python3
"""Offline audit of the saved actual generated-SQL differential and plans."""
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

root = Path(__file__).resolve().parent
source = root.parent / 'profiles/window-feed-differential.json'
data = json.loads(source.read_text())

def gm(values):
    return math.exp(statistics.fmean(math.log(x) for x in values))

def walk(node):
    yield node
    for child in node.get('Plans', []):
        yield from walk(child)

def extract(explain):
    nodes = list(walk(explain['Plan']))
    ctes = {n['Subplan Name'][4:]:n for n in nodes if n.get('Subplan Name','').startswith('CTE ')}
    fast = [n for n in nodes if n.get('One-Time Filter','').startswith('(cardinality(f.ids) = ')]
    fallback = [n for n in nodes if n.get('One-Time Filter','').startswith('((f.ids IS NULL) OR ')]
    def branch(items):
        if not items:
            return None
        assert len(items)==1
        node = items[0]
        child = node['Plans'][0]
        return {'gate_loops':node['Actual Loops'],'rows_per_gate':node['Actual Rows'],
                'child_node':child['Node Type'],'child_loops':child['Actual Loops'],
                'child_rows_per_loop':child['Actual Rows'],'shared_hits':node.get('Shared Hit Blocks',0),
                'shared_reads':node.get('Shared Read Blocks',0)}
    return {'execution_ms':explain['Execution Time'],
            'shared_hits':explain['Plan'].get('Shared Hit Blocks',0),
            'shared_reads':explain['Plan'].get('Shared Read Blocks',0),
            'temp_reads':explain['Plan'].get('Temp Read Blocks',0),
            'temp_writes':explain['Plan'].get('Temp Written Blocks',0),
            'heap_fetches_sum':sum(n.get('Heap Fetches',0) for n in nodes),
            'ctes':{k:{f:n.get(f) for f in ['Actual Rows','Actual Loops','Shared Hit Blocks','Shared Read Blocks']}
                    for k,n in ctes.items()},
            'fast':branch(fast),'fallback':branch(fallback)}

checks, cases = [], []
def check(name, condition):
    checks.append({'check':name,'pass':bool(condition)})
    assert condition, name

check('psql_success',data['psql_exit']==0)
check('31_unique_cases',len(data['summary'])==31 and len({r['case'] for r in data['summary']})==31)
check('496_results',len(data['results'])==31*16)
for summary in data['summary']:
    name = summary['case']
    entries = [r for r in data['results'] if r['case']==name]
    rows = {r['variant']:r['result'] for r in entries if r['kind']=='rows'}
    check(name+':ordered_values_equal',rows['baseline']==rows['candidate'])
    check(name+':recorded_equality_matches',summary['ordered_rows_equal'] is True)
    plans = {v:[r for r in entries if r['kind']=='plan' and r['variant']==v]
             for v in ['baseline','candidate']}
    check(name+':six_measurements_each',all(len(p)==6 for p in plans.values()))
    check(name+':repeats_0_to_5',all([r['repeat'] for r in p]==list(range(6)) for p in plans.values()))
    check(name+':alternating_ab_ba',all(r['order']==(['baseline','candidate'] if r['repeat']%2==0 else ['candidate','baseline'])
                                     for p in plans.values() for r in p))
    measured = {v:[extract(r['result'][0]) for r in p] for v,p in plans.items()}
    timing = {v:[p['execution_ms'] for p in ps] for v,ps in measured.items()}
    medians = {v:statistics.median(values) for v,values in timing.items()}
    check(name+':recorded_medians_match',all(math.isclose(medians[v],summary['median_ms'][v],rel_tol=1e-12) for v in medians))
    candidate = measured['candidate'][0]
    distinct_ids = len({r['c12'] for r in rows['candidate'] if r['c12'] is not None})
    check(name+':one_enrichment_per_actual_id',candidate['ctes']['e']['Actual Rows']==distinct_ids)
    check(name+':recent_rows_bounded',all(p['ctes']['recent']['Actual Rows']<=512 for p in measured['candidate']))
    case = {'case':name,'row_count':len(rows['candidate']),'unique_nonnull_article_ids':distinct_ids,
            'median_ms':medians,'median_ratio':medians['candidate']/medians['baseline'],
            'paired_ratio_geomean':gm([c/b for b,c in zip(timing['baseline'],timing['candidate'])]),
            'root_buffer_medians':{v:{k:statistics.median(p[k] for p in ps) for k in ['shared_hits','shared_reads','temp_reads','temp_writes','heap_fetches_sum']}
                                   for v,ps in measured.items()},
            'candidate_first_plan':candidate,
            'candidate_branch_loops_all_repeats':[{'fast':p['fast'],'fallback':p['fallback']} for p in measured['candidate']]}
    match = re.fullmatch(r'feed-(\d+)-(distinct|duplicate)-offset(\d+)',name)
    if match:
        case.update(batch_requests=int(match[1]),viewer_pattern=match[2],offset=int(match[3]))
    else:
        case.update(batch_requests=4,viewer_pattern='mixed',offset=None)
    cases.append(case)

groups = []
for pattern in ['distinct','duplicate']:
    for offset in [0,40,600]:
        selected = [r for r in cases if r['viewer_pattern']==pattern and r['offset']==offset]
        ratios = [r['median_ratio'] for r in selected]
        groups.append({'viewer_pattern':pattern,'offset':offset,'cases':len(selected),
                       'geomean_of_median_ratios':gm(ratios),'median_of_case_ratios':statistics.median(ratios),
                       'ratio_min':min(ratios),'ratio_max':max(ratios),
                       'case_weighting':'Each synthetic batch size has equal weight; not workload weighting.'})
all_plans = [extract(r['result'][0]) for r in data['results'] if r['kind']=='plan']
check('no_measured_plan_disk_reads',all(p['shared_reads']==0 for p in all_plans))
check('no_measured_plan_temp_spills',all(p['temp_reads']==p['temp_writes']==0 for p in all_plans))
check('both_fast_and_fallback_execute',any(r['candidate_first_plan']['fast']['child_loops']>0 for r in cases)
      and any(r['candidate_first_plan']['fallback']['child_loops']>0 for r in cases))
example = next(r for r in cases if r['case']=='feed-8-duplicate-offset0')
check('fallback_child_skipped_when_fast_prefix_complete',example['candidate_first_plan']['fast']['child_loops']==1
      and example['candidate_first_plan']['fallback']['child_loops']==0)
deep = next(r for r in cases if r['case']=='feed-8-distinct-offset600')
check('deep_offsets_do_not_scan_recent_window',deep['candidate_first_plan']['ctes']['recent']['Actual Loops']==0
      and deep['candidate_first_plan']['fast']['child_loops']==0)
mixed = next(r for r in cases if r['viewer_pattern']=='mixed')
check('mixed_zero_empty_deep_params_skip_window',mixed['candidate_first_plan']['ctes']['recent']['Actual Loops']==0
      and mixed['unique_nonnull_article_ids']==0)

result = {'status':'PASS_ACTUAL_SQL_DIFFERENTIAL_AND_PLAN_AUDIT','scope':data['scope'],
          'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'auditor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'source_inputs_sha256':data['inputs_sha256'],'checks':checks,'group_summaries':groups,'cases':cases,
          'limits':['No native workload or capacity was measured by this audit.',
                    'Duplicate-viewer gains are not representative of mostly distinct active VUs.',
                    'Only offsets0/40/600 plus one mixed case are measured; offsets10/20/30 are absent.',
                    'No candidate recent window exceeded200 rows in these actual plans;512 boundary has model/static coverage only.',
                    'The comparison changes simple lateral batching into sharing+window; it does not isolate window versus sharing-only.',
                    'EXPLAIN row/timing fields are instrumented and rounded; node times are inclusive and must not be added as CPU cost.',
                    'Each timing point is a warmed single-query batch under one local environment, not a maximum throughput result.']}
(root/'actual-window-audit.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['# Actual feed-window SQL diagnostic audit','',
       'All31 actual generated-SQL cases return identical ordered values. The372 measured EXPLAIN plans follow alternating AB/BA order after warmups. No measured plan reads disk or spills temporary data. This is a query diagnostic, not a native workload/capacity result.','',
       '| Viewer pattern | Offset | GM candidate/baseline median time | Interpretation |',
       '|---|---:|---:|---|']
for g in groups:
    ratio=g['geomean_of_median_ratios']
    lines.append(f"| {g['viewer_pattern']} | {g['offset']} | {ratio:.6f} | {(1-ratio)*100:.2f}% lower time |")
lines += ['', 'The distinct-viewer page1 group improves about5.0% overall, but its2-request batch regresses5.8%. Offset40 regresses at every measured size (6.5–19.3%, GM11.9%); offset600 has GM2.3% overhead. The mixed sparse/zero/deep case regresses2.8%. Duplicate cases gain81–86% in the equal-weight group summaries, mostly from deduplicating requests/counts/pages. Those gains must not be blended into a realistic unique-user headline.', '',
          '| Case | Baseline ms | Window ms | Time change | Fast / fallback child loops | Recent rows | Unique enriched IDs |',
          '|---|---:|---:|---:|---:|---:|---:|']
for r in cases:
    p=r['candidate_first_plan']
    lines.append(f"| {r['case']} | {r['median_ms']['baseline']:.4f} | {r['median_ms']['candidate']:.4f} | {(r['median_ratio']-1)*100:+.2f}% | {p['fast']['child_loops']} / {p['fallback']['child_loops']} | {p['ctes']['recent']['Actual Rows']} | {r['unique_nonnull_article_ids']} |")
lines += ['', 'Actual branch witnesses:', '',
          '- N8/distinct/offset0 executes the fast child2 times and indexed fallback6 times. At offset40 it executes fast0/fallback8: the extra window does not fill the requested prefix.',
          '- N8/duplicate/offset0 executes one deduplicated fast page and no fallback child. This confirms the one-time filter prevents the indexed branch from running when the prefix is complete.',
          '- Deep offset600 and the mixed sparse/zero/deep case skip the recent CTE entirely (Actual Loops0), then retain the indexed fallback and synthetic empty-page rows.',
          '- Every candidate enrichment CTE returns exactly the number of distinct non-null article IDs in that case’s output.', '',
          'Selection implication: measure sharing-only separately before deciding whether the recent-window complexity helps. Current evidence favors testing READ_BATCH_US independently, and either sharing-only or a first-page-only window variant as the next whole-workload comparison. The full original window is not a consistent query win for distinct viewers.', '',
          'Limitations: '+ ' '.join(result['limits'])]
(root/'actual-window-audit.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'status':result['status'],'checks':len(checks),'groups':groups}))
