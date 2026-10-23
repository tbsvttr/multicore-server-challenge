#!/usr/bin/env python3
from pathlib import Path
import json,re,hashlib,datetime,collections
root=Path('/private/tmp/multicore-comparison-20261023');inv=root/'inventory';loc=json.loads((inv/'source-locations.json').read_text());main=loc['upstream_commit'];tree=json.loads((inv/'main-actual-tree-raw.json').read_text());tree_by={x['path']:x for x in tree['tree']};prs=json.loads((inv/'pulls-raw.json').read_text());pr_by={p['number']:p for p in prs};heads={e['pr']:e for e in json.loads((inv/'head-source-manifest.json').read_text())['entries']};src=Path(loc['upstream_source_root']);now=datetime.datetime.now(datetime.timezone.utc).isoformat()
lang={1:'Rust',2:'V',4:'C++',5:'C',7:'Rust',8:'C#',9:'Swift',10:'C',11:'Rust',12:'Elixir',13:'Python',14:'C#',15:'COBOL',16:'D',17:'D',18:'D',19:'Lua',20:'C#',21:'Pony',22:'C#',23:'Perl',24:'Pony',25:'Rust',26:'TypeScript/Bun',27:'Go',28:'Go',29:'Kotlin',30:'Kotlin',31:'Goose',32:'Goose'}
score_rows=[];not_scored={}
for line in (inv/'LEADERBOARD.md').read_text().splitlines():
 if not line.startswith('|'):continue
 cells=[c.strip() for c in line.strip('|').split('|')]
 if cells[0].isdigit() and len(cells)==10:
  num=re.search(r'\[#(\d+)\]',cells[3]);name=re.search(r'\[([^]]+)\]',cells[2]).group(1)
  pr=int(num.group(1)) if num else None
  example=re.search(r'\((examples/[^)]+)\)',cells[2])
  score_rows.append({'pr':pr,'name':name,'example_folder':example.group(1) if example else None,'official_score':{'rank':int(cells[0]),'users':int(re.sub(r'[^0-9]','',cells[1])),'requests_per_second':float(cells[5].replace(',','')),'p95_ms':float(cells[6]),'p99_ms':float(cells[7]),'front':cells[4],'cpu_app_postgres':cells[8],'note':cells[9]}})
 elif len(cells)==3 and (n:=re.search(r'\[#(\d+)\]',cells[1])):
  not_scored[int(n.group(1))]=cells[2]
assert len(score_rows)==29 and sum(r['pr'] is None for r in score_rows)==4
scores={r['pr']:r['official_score'] for r in score_rows if r['pr'] is not None}
base_url=f'https://github.com/arjaythedev/multicore-server-challenge/tree/{main}'
records=[]
def scripts_at(folder):
 return {name:{'exists':(folder/name).is_file(),'sha256':hashlib.sha256((folder/name).read_bytes()).hexdigest() if (folder/name).is_file() else None} for name in ['install.sh','build.sh','start.sh','README.md']}
for pr in sorted(prs,key=lambda p:p['number']):
 n=pr['number'];h=heads[n];folder='submissions/'+h['folder'];state='merged' if pr['merged_at'] else pr['state'];active=state!='closed';merged=state=='merged';canonical_dir=src/folder if merged else Path(h['source_dir']);canonical_ref=main if merged else h['head'];canonical_repo='arjaythedev/multicore-server-challenge' if merged else h['tree_api_repository'];subtree=tree_by[folder]['sha'] if merged else h['submission_tree_sha']
 changes=[]
 if merged and subtree!=h['submission_tree_sha']:
  ht=json.loads(Path(h['tree_file']).read_text());hb={e['path']:e for e in ht['tree']}
  changes=[path for path in sorted(set(tree_by)|set(hb)) if path.startswith(folder+'/') and tree_by.get(path,{}).get('sha')!=hb.get(path,{}).get('sha')]
 records.append({'id':f'pr-{n}','pr':n,'pr_url':pr['html_url'],'name':h['folder'],'variant':('Vibe.D standard' if n==17 else 'Vibe.D light' if n==18 else None),'language':lang[n],'state':state,'draft':pr.get('draft',False),'active':active,'is_ours':n==32,'head_repository':(pr['head']['repo'] or {}).get('full_name'),'head_commit':h['head'],'head_root_tree':h['root_tree_sha'],'head_submission_tree':h['submission_tree_sha'],'source_folder':folder,'canonical_source_ref':canonical_ref,'canonical_source_tree':subtree,'canonical_source_kind':'current_upstream_main' if merged else 'open_pr_head' if active else 'closed_historical_head','canonical_source_url':f'https://github.com/{canonical_repo}/tree/{canonical_ref}/{folder}','local_source_dir':str(canonical_dir),'canonical_matches_pr_submission_tree':subtree==h['submission_tree_sha'],'canonical_changes_from_pr_head_paths':changes,'scripts':scripts_at(canonical_dir),'official_score':scores.get(n),'official_unscored_reason':not_scored.get(n),'local_run_this_refresh':'NOT_RUN','measured_source_revision_known':False,'score_source_pin_caveat':'Official scoreboard values and current source pins are separate evidence; the scoreboard does not identify the exact scored commit.'})
for r in score_rows:
 if r['pr'] is not None:continue
 folder=r['example_folder'];name=r['name'];language={'examples/go':'Go','examples/java':'Java','examples/rust':'Rust','examples/python':'Python'}[folder]
 records.append({'id':folder.replace('/','-'),'pr':None,'pr_url':None,'name':name,'variant':'original reference example, officially rerun','language':language,'state':'reference','draft':False,'active':True,'is_ours':False,'head_commit':None,'source_folder':folder,'canonical_source_ref':main,'canonical_source_tree':tree_by[folder]['sha'],'canonical_source_kind':'current_upstream_example','canonical_source_url':base_url+'/'+folder,'local_source_dir':str(src/folder),'scripts':scripts_at(src/folder),'official_score':r['official_score'],'official_unscored_reason':None,'local_run_this_refresh':'NOT_RUN','measured_source_revision_known':False,'score_source_pin_caveat':'Official scoreboard values and current source pins are separate evidence; the scoreboard does not identify the exact scored commit.'})
summary={'pr_records':30,'merged_prs':21,'open_prs':6,'closed_historical_prs':3,'active_submission_prs_including_ours':27,'active_competitors_excluding_ours':26,'reference_examples':4,'official_scored_rows':29,'official_scored_submission_prs':25,'active_unscored_prs':[5,17],'historical_closed_prs':[14,18,21],'canonical_main_submissions_differing_from_head_tree':[r['pr'] for r in records if r.get('canonical_changes_from_pr_head_paths')]}
inventory={'created_at_utc':now,'upstream_commit':main,'upstream_git_tree':loc['upstream_tree'],'scope':'Current merged submissions and every open PR, plus four reference examples; closed PRs remain historical records only. No install/build/run performed.','summary':summary,'records':records}
(inv/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
ours=scores[32]['users'];leader=max(s['users'] for s in scores.values());bypr={r['pr']:r for r in records if r['pr'] is not None};rows=[]
for sr in score_rows:
 r=bypr[sr['pr']] if sr['pr'] is not None else next(r for r in records if r['source_folder']==sr['example_folder']);s=sr['official_score'];rr=dict(r);rr['gap_users_vs_ours']=s['users']-ours;rr['gap_percent_vs_ours']=100*(s['users']/ours-1);rr['gap_users_vs_leader']=s['users']-leader;rr['gap_percent_vs_leader']=100*(s['users']/leader-1);rows.append(rr)
for n in [5,17]:
 rr=dict(bypr[n]);rr.update({k:None for k in ['gap_users_vs_ours','gap_percent_vs_ours','gap_users_vs_leader','gap_percent_vs_leader']});rows.append(rr)
historical=[bypr[n] for n in [14,18,21]]
comparison={'snapshot_at_utc':now,'upstream_commit':main,'upstream_git_tree':loc['upstream_tree'],'leaderboard_blob_sha1':tree_by['LEADERBOARD.md']['sha'],'leaderboard_sha256':hashlib.sha256((inv/'LEADERBOARD.md').read_bytes()).hexdigest(),'leaderboard_url':f'https://github.com/arjaythedev/multicore-server-challenge/blob/{main}/LEADERBOARD.md','publication_path':'benchmarks/2026-10-23/README.md','source_inventory':'inventory/inventory.json','summary':summary,'official_protocol':'8 dedicated vCPU / 16 GB; application, optional Nginx and PostgreSQL18 on the target; full seed; separate-machine load generation; highest users held for five minutes with p95<500ms,p99<1000ms,errors<1%.','comparison_scope':'Maintainer-published official batch, not a new Mac benchmark. Each latency/RPS value is measured at that implementation\'s own scored user count; do not interpret these as matched-load relative latency/RPS.','gap_definition':'Signed users difference: row users minus reference users; percentage is 100*(row/reference-1), using ours65000 or leader100000 as denominator. Unscored entries have null gaps.','ours_reference':{'pr':32,'users':ours,'rank':scores[32]['rank'],'head':bypr[32]['head_commit'],'draft':bypr[32]['draft']},'leader_reference':{'pr':7,'users':leader,'rank':1},'raw_trial_limitation':'Leaderboard says per-trial/probe/hold histograms and CPU records can be shared on request; they are not included in this public snapshot. No request/message was sent.','rows':rows,'historical_closed_records':historical,'no_new_local_benchmarks':True}
(root/'official-comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
def gap(v,p):return f'{v:+,} ({p:+.2f}%)'
def label(r):
 if r['pr'] is not None:return f"[#{r['pr']} {r['name']}]({r['pr_url']})"+(' **(ours)**' if r['pr']==32 else '')
 return f"[{r['name']}]({r['canonical_source_url']})"
lines=['# Official multicore comparison — 23 October 2026','',f"Snapshot: {now}. The [maintainer’s official leaderboard]({comparison['leaderboard_url']}) already compares all 29 scored implementations/examples on the same challenge box. This record adds the two active submissions without a score, giving one row for each of the 31 current implementations/examples. It does not rerun them on the Mac.",'',
'Our Goose is **#8 at 65,000 users**, compared with Rust #7 at **100,000 users**. Goose holds 35,000 fewer users (35.00% below the leader); matching 100,000 would require 53.85% more users than its current score. Goose #31 holds 62,000 users. Our PR remains a draft at source `3e908747`; the tested proposal to change local defaults was not applied.','',
'The official conditions are 8 dedicated vCPUs and 16 GB, with the application, PostgreSQL 18 and any Nginx sharing the target budget, full seed, and load generation on another machine. Score is the highest user count sustained for a five-minute run with p95 <500 ms, p99 <1 s and <1% errors.','',
'**Latency and request rate are measured at each row’s own scored load. They are not matched-load latency or throughput comparisons.** The two gap columns compare scored user counts: signed row minus reference, with percentages relative to our 65,000 or the leader’s 100,000. Unscored means unknown, not zero.','',
'| Official rank | Implementation | Status | Users | Gap vs ours | Gap vs leader | Req/s | p95 / p99 ms | Front | CPU app / PG | Caveat |','|---:|---|---|---:|---:|---:|---:|---:|---|---|---|']
for r in rows:
 s=r['official_score'];state='merged' if r['state']=='merged' else 'open draft' if r['draft'] else 'open' if r['state']=='open' else 'reference'
 if s:
  lines.append(f"| {s['rank']} | {label(r)} | Scored; {state} | {s['users']:,} | {gap(r['gap_users_vs_ours'],r['gap_percent_vs_ours'])} | {gap(r['gap_users_vs_leader'],r['gap_percent_vs_leader'])} | {s['requests_per_second']:,.0f} | {s['p95_ms']:g} / {s['p99_ms']:g} | {s['front']} | {s['cpu_app_postgres']} | {s['note'] or '—'} |")
 else:
  desc=(r['official_unscored_reason'] or 'No published official score in this snapshot.').replace('|','/')
  if r['pr']==17:desc='Vibe.D standard variant; no published official score. Distinct from closed light variant #18.'
  lines.append(f"| — | {label(r)} | Unscored; {state} | — | — | — | — | — | — | — | {desc} |")
lines += ['',
'Closed historical variants are excluded from the current table. [D Vibe.D light #18](https://github.com/arjaythedev/multicore-server-challenge/pull/18) is a separate variant from open standard #17; the maintainer reports SIGILL 11 minutes into an 8,000-user run and unpinned dependencies, so it has no official passing score. Closed predecessors [#14](https://github.com/arjaythedev/multicore-server-challenge/pull/14) and [#21](https://github.com/arjaythedev/multicore-server-challenge/pull/21) are retained in the JSON history and source inventory.','',
f"Sources are pinned at upstream commit [`{main[:8]}`](https://github.com/arjaythedev/multicore-server-challenge/tree/{main}), actual Git tree `{loc['upstream_tree']}`, and leaderboard blob `{tree_by['LEADERBOARD.md']['sha']}`. [Machine-readable comparison](official-comparison.json) and [source inventory](inventory/inventory.json) retain PR heads, canonical source folders/trees, script hashes, state and caveats. Current source pins do not prove the exact revision used for a historical score. Merged Rust #11 and #25 have upstream build-script changes relative to their PR heads; those paths are explicitly recorded.",'',
'The maintainer says raw probe/hold and per-endpoint/CPU records are available on request; those trial files are not public in this snapshot. No new request was sent. Previous local experiments remain historical evidence and do not replace the official batch above.']
(root/'official-comparison.md').write_text('\n'.join(lines)+'\n')
# Small human-readable inventory summary; detailed dependency/ARM review is separately owned.
groups=collections.defaultdict(list)
for r in records:
 if r['active']:groups[r['language']].append(r['id'])
summary_lines=['# Pinned implementation inventory','',f'Snapshot {now}; upstream `{main}`, actual Git tree `{loc["upstream_tree"]}`.','',f'{len(prs)} PR records: 21 merged, 6 open, 3 closed historical. Current coverage is 27 submission PRs including ours, plus4 reference examples. Official scored rows29; active unscored PRs5 and17. No build or benchmark was run.','', '| Language/build group | Current entries |','|---|---|']
summary_lines += ['| '+k+' | '+', '.join(v)+' |' for k,v in sorted(groups.items())]
summary_lines += ['', 'Canonical source for merged entries is current upstream main. Open and closed heads are separate snapshots under `sources/pr-N-SHA/`; all source paths and script hashes are in `inventory.json`. Closed #14/#18/#21 are historical only. Official scores are separate fields from current source pins.','', 'All 21 merged source trees match their PR-head submission trees except Rust #11 and #25, whose build.sh changed in upstream main. No source was modified by this preparation. The detailed ARM/dependency review is under the separately prepared build-plans directory.']
(inv/'README.md').write_text('\n'.join(summary_lines)+'\n')
print('Wrote inventory/inventory.json, inventory/README.md, official-comparison.md/json')
print(json.dumps(summary,indent=2));print('Current comparison rows',len(rows));print('Ours score',scores[32])
