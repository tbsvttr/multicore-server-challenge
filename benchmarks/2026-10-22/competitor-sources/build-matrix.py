from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re

root=Path('/private/tmp/multicore-research-20261022');raw=root/'competitor-sources'
prs=json.loads((raw/'prs.json').read_text());readmes={v['pr']:v for v in json.loads((raw/'readme-fetch-manifest.json').read_text())}
upstream=json.loads((raw/'upstream-main.json').read_text())['sha']
leaderboard_url=f'https://github.com/arjaythedev/multicore-server-challenge/blob/{upstream}/LEADERBOARD.md'
official={}
for line in (raw/'LEADERBOARD.md').read_text().splitlines():
    if not re.match(r'^\| \d+ \|',line):continue
    cells=[c.strip() for c in line.strip().strip('|').split('|')]
    number=int(re.search(r'\[#(\d+)\]',cells[3]).group(1))
    official[number]={'type':'OFFICIAL_LEADERBOARD','rank':int(cells[0]),'users':int(cells[1].replace('*','').replace(',','')),'requests_per_second':float(cells[5].replace(',','')),'p95_ms':float(cells[6]),'p99_ms':float(cells[7]),'front':cells[4],'cpu_app_postgres':cells[8],'qualification_note':cells[9] if len(cells)>9 else '', 'protocol':'Official dedicated8-vCPU/16-GB Ubuntu24 x86_64 target, PostgreSQL18 and app together, full seed, remote load generators; highest passing5-minute hold after warm-up/probes; p95<500ms,p99<1000ms,errors<1%.','source_url':leaderboard_url,'measured_full_commit_sha':None}
    official[number]['protocol']=official[number]['protocol'].replace('dedicated8','dedicated 8').replace('passing5','passing 5')
    p=next(p for p in prs if p['number']==number)
    comments=[c for c in p.get('comments',[]) if c.get('author',{}).get('login')=='arjaythedev' and 'Benchmarked on' in c.get('body','')]
    if comments:
        official[number]['maintainer_confirmation_url']=comments[-1]['url']
        if re.search(r'0% errors|0 errors',comments[-1]['body']): official[number]['errors_percent']=0
    if number==24: official[number]['measured_commit_prefix']='a38283c'

claims={}
def add(n,summary,protocol,metrics=None,notes=None,location='readme'):
    p=next(p for p in prs if p['number']==n);r=readmes[n]
    url=p['url'] if location=='body' else f"https://github.com/{r['repo']}/blob/{r['sha']}/{r['path']}"
    claims.setdefault(n,[]).append({'type':'SELF_REPORTED','summary':summary,'protocol':protocol,'metrics':metrics or [],'notes':notes or [],'source_url':url,'measured_full_commit_sha':None})

def point(users=None,rps=None,p95=None,p99=None,errors=None,verdict='reported pass',**extra):
    return {'users':users,'requests_per_second':rps,'p95_ms':p95,'p99_ms':p99,'errors_percent':errors,'verdict':verdict,**extra}

add(1,'7,000 users ×0.1;17,100 req/s;197/576ms p95/p99.','Apple-silicon Docker;app+PostgreSQL8 vCPUs;full seed;loadgen4 other vCPUs;20s ramp+40s measured;think-scale0.1.',[point(7000,17100,197,576,0)],['Accelerated think time;not an official capacity score.'])
add(2,'4,000 users ×0.2;README5,133 req/s;description4,875 req/s.','Shared24-thread development host including app,PostgreSQL and generator;full seed;60s ramp+5-minute hold;think-scale0.2.',[point(4000,5133,126.1,487.7,0)],['PR description reports a different4,875-req/s trial;neither is official.'])
add(2,'Description trial:4,000 users ×0.2;4,875 req/s.','Same-host development hold;5 minutes;think-scale0.2.',[point(4000,4875,392.7,915.5,0)],location='body')
add(4,'~35,000 req/s,p99~20ms;140k users is extrapolated.','Ryzen7700X;app+PostgreSQL pinned to4 cores/8 threads;full seed;pgtune settings;generators on other threads;duration unspecified.',[point(rps=35000,p99=20,verdict='approximate passing-throughput claim')],['Do not treat extrapolated140k as measured concurrent users.'])
add(5,'64,000 users,p95/p99 143/443ms,0% errors.','2% development seed,same-host generator;duration not specified in PR body.',[point(64000,p95=143,p99=443,errors=0)],['Official attempt later had no passing5-minute hold;see official-attempt note.'],location='body')
add(7,'92,000-user5-minute hold;23,256 req/s;408/509ms;0 errors.','MEGASERVER XeonE5-2690v3;app+PostgreSQL share8-CPU quota/16GiB;full repository scorer;same-physical-host generators;no affinity.',[point(92000,23256,408,509,0)],['Local author measurement,distinct from official100k result.'],location='body')
add(8,'125,000-user screen;32,400 req/s;192/231ms;0 errors.','GCP c4-highcpu-8 target,full seed,remote two-load-box rig;fresh DB,3min warm-up,60s ramp+60s measured;think-scale1.',[point(125000,32400,192,231,0)],['Rig connection ceiling125k;not a5-minute hold.','README says the replacement bcrypt library in the latest source has not run on that rig;reported numbers are for an earlier bcrypt implementation.'])
add(9,'10,000-user screen;2,644 req/s;27.7/187ms;0 errors.','MacBook:app+PostgreSQL18+loadgen together;development seed10,000 articles;probe duration unspecified.',[point(10000,2644,27.7,187,0)],['20k failed generator ports;does not establish server capacity.'],location='body')
add(10,'10,000 users ×0.1;12,800 req/s;458/485ms;0 errors.','i5-9500 VM;server+PostgreSQL pinned4 CPUs,loadgen2 CPUs;full seed;3min warm-up+5-minute hold;think-scale0.1.',[point(10000,12800,458,485,0)],['Separate150k-connection screen used think-scale4 and is not a150k default-workload capacity score.'])
add(11,'Published-head76,000-user probe;20,140.5 req/s;9.4/22.6ms.','M1Pro ARM64 Linux VM;app+PostgreSQL4 CPUs,loadgen6 CPUs;full seed;60s ramp+60s measured+15s tail;local affinity split.',[point(76000,20140.5,9.4,22.6,0)],['README also includes an earlier80k probe on a different revision;no5-minute hold for these published-head probes.'])
p11=next(p for p in prs if p['number']==11)
c11=next(c for c in p11['comments'] if 'Updated local benchmark results' in c['body'])
claims[11].append({'type':'SELF_REPORTED_UNCOMMITTED_SOURCE','summary':'Separate uncommitted follow-up:two96k-user holds at25,405.33/25,409.17 req/s.','protocol':'Same M1Pro physical host;server VM8vCPU/16GiB,generator VM4vCPU/4GiB;full fresh seed,60s ramp+300s measured;think-scale1.','metrics':[point(96000,25405.33,10.351,20.559,0),point(96000,25409.17,9.335,18.703,0),point(128000,29153.41,2096.127,10002.431,2.9351,verdict='FAIL')],'source_archive_sha256':'c610fb0ef60cea93f8e28184bee7da8f86398545cd6e48d272c0f958e4e45765','measured_full_commit_sha':None,'source_url':c11['url'],'notes':['Not the published PR head.','A128k hold with4-GiB generator RAM was invalidated by OOM;the8-GiB retry failed SLOs.']})
add(12,'Two33,000-user holds:8,229.92/8,103.53 req/s;p95 443/474ms.','M1Pro ARM VM;app+PostgreSQL4 CPUs,loadgen6 CPUs;full fresh seed;300-user warm-up,60s ramp+nominal300s measured+15s tail;explicit tuned profile.',[point(33000,8229.92,443.135,496.383,0),point(33000,8103.53,474.111,527.359,0)],['34k failed;local4-core profile,not default8-core capacity.','README discloses wall-clock corrections and nominal denominator,limiting throughput precision.'])
add(13,'5,400 users ×0.2;6,364–6,421 req/s;p95 185–215ms.','4-vCPU test VM shared by app,PostgreSQL and generator;full seed;30s measured;think-scale0.2;PostgreSQL SSL on.',[point(5400,rps=None,p95=215,p99=290,verdict='reported pass',rps_range=[6364,6421])],['8-vCPU extrapolations are not measured scores.'])
add(14,'60,000-user5-minute hold;~15,400 req/s;281/419ms;0.05% errors.','Azure Standard_D8as_v5 target,EPYC7763,8vCPU/~16GB;full seed;three remote D4 load boxes;repository search;60k passing/62k failing bracket.',[point(60000,15400,281,419,0.05)],['Closed historical PR;not a current active submission.'])
for n in (17,18):
    add(n,'8,000-user dev-seed screen;2,118 req/s;116/234ms.','Laptop;development seed;same local generator;duration/resource split unspecified.',[point(8000,2118,116,234),point(12000,p95=116,errors=28,verdict='FAIL:connection timeouts')],['Same README measurement table appears on the distinct standard/light variants;does not independently establish each current variant capacity.'])
add(19,'9,000-user5-minute hold;210/572ms;0 errors.','DigitalOcean4-vCPU/8GB shared-vCPU droplet,full seed;remote generator;five-minute fresh-seed hold;4–10% steal reported.',[point(9000,p95=210,p99=572,errors=0)],['Half-sized target;not official8-core score.'])
add(20,'12,000-user5-minute hold;3,152 req/s;125/287ms;0 errors.','GCP c4-highcpu-8 target,full seed,remote generator;repository box setup;3min warm-up,60s ramp+5min hold;think-scale1.',[point(12000,3152,125,287,0)],['Different hardware from official8,300-user result;near-limit probes varied.'])
add(24,'More than30% ahead of provided examples;no absolute local score supplied.','Author test environment and exact duration not specified.',notes=['Official25k result is explicitly for earlier commit a38283c;rerun of latest head is queued.'],location='body')
add(25,'101,080 equivalent users ×0.1 (~17,500 req/s);not101k real users.','Ryzen5900X;app+PostgreSQL8 pinned hardware threads;generators on16 other threads;full seed;five-minute hold;think-scale0.1.',[point(rps=17500,p95=251,p99=278,errors=0,equivalent_users=101080,think_scale=0.1),point(101080,17900,2200,2300,verdict='FAIL at think-scale1'),point(128000,16000,5900,6500,verdict='FAIL at think-scale1')],['Author explicitly warns equivalent-user scaling overstates capacity;~60k real users is an extrapolation,not a qualifying hold.'])
add(26,'10,000-user exploratory pass;4.1/40.4ms;0 errors.','MacBookAirM2;DockerPostgreSQL18;full seed;think-scale1;duration unspecified,no5-minute hold claimed.',[point(10000,p95=4.1,p99=40.4,errors=0)],['20k/40k attempts hit macOS descriptors/connections;not server capacity failures.'])
add(27,'67,500 users behind Nginx;17,780 req/s;49/77ms.','Local60-second screens;app+PostgreSQL8 cores/16GB;Nginx shares cores with separate2GB cap;not official hardware.',[point(67500,17780,49,77,0),point(100000,25818,318,360,0,configuration='direct,no Nginx')],['Submitted Front is nginx;direct result is a separate mode.','Near-limit repeats vary;no5-minute capacity hold.'])
add(28,'Historical135,000-user screen;33,645 req/s;386/452ms;did not repeat.','Local60-second screens;app+PostgreSQL8 cores/16GB;not official hardware.',[point(135000,33645,386,452,0,verdict='single reported pass;repeat latency failures')],['Pinned README explicitly says the135k result did not repeat:old/new builds missed latency with0 errors.'])
add(29,'18,000 users;15,700 req/s;19k failed.','Local warmed Docker comparison to Java example;app+PostgreSQL8 cores/full seed,generator8 other cores;measurement duration and think-scale unspecified.',[point(18000,15700)],['Cannot compare user counts without the missing workload timing details.'])
add(30,'19,000 users;16,900 req/s.','Local warmed Docker comparison to Java example;app+PostgreSQL8 cores/full seed,generator8 other cores;measurement duration and think-scale unspecified.',[point(19000,16900)],['README documents non-atomic article creation;conformance pass alone does not settle that rule deviation.'])
add(31,'160,000-user screen;41,249 req/s;368/501ms;0 errors.','GCP c4-highcpu-8 target,full seed,two remote load boxes;fresh DB,60s ramp+60s measured;think-scale1.',[point(160000,41249,368,501,0),point(175000,41500,967,2818,0,verdict='FAIL latency')],['No5-minute hold or scored warm-up on grown database claimed.','Our planned reference additionally discloses necessary ARM ABI and correctness fixes;it is not a stock official PR31 score.'])

not_scored={5:'Maintainer: no5-minute hold passed;POST /api/articles~2s even idle;2-minute100-user probes passed but sustained p99 failed.',18:'Maintainer: SIGILL crash11minutes into an8,000-user run;dependencies also need pinning.'}
comparison_plan={7:'PLANNED_NOT_YET_COMPARED',31:'PLANNED_CORRECTED_REFERENCE_NOT_YET_COMPARED'}
rows=[]
for p in sorted(prs,key=lambda p:p['number']):
    n=p['number'];paths=sorted(set(f['path'].split('/')[1] for f in p['files'] if f['path'].startswith('submissions/')))
    name=paths[0] if paths else p['title'];variant={17:'standard Vibe.D',18:'Vibe.D-light',21:'closed predecessor of PR24',14:'closed ASP.NET predecessor',32:'our candidate'}.get(n)
    r=readmes[n];url=f"https://github.com/{r['repo']}/tree/{p['headRefOid']}/submissions/{name}"
    comparison='SELF_ONLY_BATCHING_ABLATION_IN_PROGRESS' if n==32 else comparison_plan.get(n,'NOT_COMPARED')
    row={'pr':n,'implementation':name,'variant':variant,'pr_state':p['state'],'pr_url':p['url'],'author':p['author']['login'],'source':{'pr_head_sha':p['headRefOid'],'head_repository':p['headRepository']['nameWithOwner'] if p.get('headRepository') else None,'pinned_source_url':url,'pinned_readme_url':f"https://github.com/{r['repo']}/blob/{r['sha']}/{r['path']}",'updated_at':p['updatedAt'],'head_pin_caveat':'This pins the inventoried source,not necessarily the revision measured in historical official/self-reported results.'},'official_result':official.get(n),'official_unsuccessful_attempt':not_scored.get(n),'self_reported_results':claims.get(n,[]),'our_comparison':{'completed':False,'status':comparison,'result':None},'active_competitor':n!=32 and p['state']!='CLOSED'}
    if n==32:row['notes']=['197/197 conformance and primitive/security checks are correctness evidence,not a competitor speed comparison.','Current same-source ARTICLE_BATCH ablation is not an exhaustive comparison or an official score.']
    if n==21:row['notes']=['Author explicitly points to replacement PR24;excluded from active competitor count.']
    if n==14:row['notes']=['Closed;kept only as historical inventory evidence.']
    if not row['self_reported_results']:row.setdefault('notes',[]).append('No absolute self-reported performance result found in inspected PR body/comments/pinned README.')
    rows.append(row)
# Normalize compact hand-written notes into readable prose without changing data.
def spaces(v):
    if isinstance(v,str):
        v=re.sub(r'(?<=[A-Za-z])(?=\d)', ' ',v) if not v.startswith(('http:','https:')) and len(v)!=40 and not re.fullmatch('[a-f0-9]+',v) else v
        v=v.replace(';not','; not').replace(';app','; app').replace(';full','; full').replace(';duration','; duration').replace(';same','; same').replace(';no','; no').replace('CPU/','CPU / ').replace('GB ','GB ')
        return v
    if isinstance(v,list):return [spaces(x) for x in v]
    if isinstance(v,dict):return {k:spaces(x) for k,x in v.items()}
    return v
# Do not transform names, URLs, commit hashes or identifiers. Human note spacing
# is corrected narrowly below, preserving all source pins.
def tidy_prose(text):
    text=re.sub(r';(?=\S)','; ',text)
    text=re.sub(r',(?=[A-Za-z])',', ',text)
    text=re.sub(r'(?<=[A-Za-z]),(?=\d)',', ',text)
    text=re.sub(r':(?=[A-Za-z0-9])',': ',text)
    text=re.sub(r'(?<=\d)(?=(?:ms|min|s|GB|GiB|vCPU|vCPUs|CPUs|CPU|cores|minutes|threads)\b)',' ',text)
    text=re.sub(r'\b(no|not|at|in|with|after|before|only|share|shared|remaining|contains|above|below|all|passed|failed|crash|for|an|README|description|two|three|four|from|loadgen)(?=\d)',r'\1 ',text,flags=re.I)
    for first,second in [('PostgreSQL8','PostgreSQL 8'),('PostgreSQL4','PostgreSQL 4'),('PostgreSQL18','PostgreSQL 18'),('DigitalOcean4','DigitalOcean 4'),('Ryzen7700X','Ryzen 7700X'),('Ryzen5900X','Ryzen 5900X'),('M1Pro','M1 Pro'),('8vCPU','8 vCPU'),('4vCPU','4 vCPU'),('4GiB','4 GiB'),('5-minute100','5-minute 100'),('8,000-user','8,000-user'),('full seed,two','full seed, two'),('app+PostgreSQL','app + PostgreSQL'),('think-scale0.1','think-scale 0.1'),('think-scale0.2','think-scale 0.2'),('think-scale1','think-scale 1'),('No5-minute','No 5-minute'),('no5-minute','no 5-minute'),('-user5-minute','-user 5-minute'),('Published-head76','Published head 76'),('GCP8','GCP 8'),('default-scale101k','default-scale 101k'),('1,024','1,024')]:
        text=text.replace(first,second)
    return text
for row in rows:
    for claim in row['self_reported_results']:
        for key in ('summary','protocol'):
            claim[key]=tidy_prose(claim[key])
        claim['notes']=[tidy_prose(x) for x in claim.get('notes',[])]
    if row['official_unsuccessful_attempt']:
        row['official_unsuccessful_attempt']=tidy_prose(row['official_unsuccessful_attempt'])
    if row['pr']==7:row['our_comparison']['status']='IN_PROGRESS_RESULT_PENDING'
    if row['pr']==31:row['our_comparison']['status']='CORRECTED_REFERENCE_CONFORMANCE_PASSED_NOT_COMPARED'
    if row['pr']==32:
        row['our_comparison']['status']='OWN_ABLATION_ONLY_RUST_COMPARISON_IN_PROGRESS'
        row['notes']=['Correctness and same-source ARTICLE_BATCH ablation do not establish superiority over another PR.','Frozen 80k-user Rust7 comparison is in progress; no completed result is inventoried.']

examples=[]
for language,score in [('go',22000),('java',21000),('rust',19000),('python',10000)]:
    examples.append({'implementation':'examples/'+language,'reported_video_users':score,'type':'VIDEO_HARDWARE_REFERENCE','protocol':'Original DigitalOcean PremiumAMD video8-vCPU setup;README explicitly says not directly comparable to current challenge box.','our_comparison_completed':False,'source_url':f'https://github.com/arjaythedev/multicore-server-challenge/blob/{upstream}/examples/{language}/README.md'})
upstream_folders=[x['name'] for x in json.loads((raw/'upstream-submissions.json').read_text()) if x['type']=='dir']
summary={'all_pr_records':len(rows),'open_prs':sum(x['pr_state']=='OPEN' for x in rows),'merged_prs':sum(x['pr_state']=='MERGED' for x in rows),'closed_historical_prs':sum(x['pr_state']=='CLOSED' for x in rows),'upstream_merged_submission_folders':len(upstream_folders),'active_competitors_excluding_ours':sum(x['active_competitor'] for x in rows),'published_official_scores':len(official),'active_competitors_without_published_official_score':sum(x['active_competitor'] and x['official_result'] is None for x in rows),'completed_our_competitor_comparisons':0,'planned_our_competitor_comparisons':[31],'in_progress_our_competitor_comparisons':[7],'all_competitor_superiority_proven':False,'official_first_place_for_ours':False}
record={'created_at_utc':datetime.now(timezone.utc).isoformat(),'upstream_main_sha':upstream,'source_scope':'All30PRs returned by gh,all30pinned submission READMEs,PR bodies/comments,current pinned leaderboard,and current upstream submissions directory;local lab comparison status from active work.','summary':summary,'conclusion':'No evidence presently establishes our Goose as faster than every competitor. Rust7 comparison is in progress and corrected portable Goose31 comparison is planned;all other active competitors remain untested by us. Official first place requires maintainer scoring under the official protocol.','source_pin_policy':'LatestPRheads are pinned independently from historical result revisions. Do not attach official scores to those exact heads without a measured-source witness. Pony24 is explicitly scored at older a38283c. Self-reported numbers use heterogeneous hardware,durations,think scales and revisions;do not merge them into one speed ranking.','upstream_submission_folders':upstream_folders,'competitors':rows,'reference_examples':examples,'source_snapshots':[{'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(raw.iterdir()) if p.is_file() and p.name!='build-matrix.py']}
(root/'competitors.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')

def fmt(n):return f'{n:,.0f}' if n is not None else '—'
def clean(s):return s.replace('|','/').replace('\n',' ')
md=['# Multicore competitor evidence inventory','',f'Snapshot: upstream `{upstream}`. {summary["all_pr_records"]} PR records:16open,12merged,2closed;27active competitors excluding ours. The current leaderboard contains17official scores.','', '**We have not completed a controlled performance comparison against another multicore PR yet.** Rust #7 comparison is in progress; a disclosed portable/corrected Goose #31 comparison is planned. Same-source article-batching tests, 197-step conformance passes and single-core results do not prove superiority over those competitors or the remaining25active submissions.','',f'The [official leaderboard]({leaderboard_url}) measures dedicated8-vCPU/16-GB x86_64 capacity with a remote generator and a passing5-minute hold. PR head pins below identify source inventory;they do not independently prove which revision produced historical scores. Self-reported screens/holds are heterogeneous and are not sorted as a speed ranking.','', '| PR / implementation | Inventoried head | Official five-minute result | Self-reported evidence / limitation | Our comparison |','|---|---|---|---|---|']
for row in sorted(rows,key=lambda x:(x['pr_state']=='CLOSED',x['pr']==32,x['official_result'] is None,x['official_result']['rank'] if x['official_result'] else 999,x['pr'])):
    n=row['pr'];name=row['implementation'];name+=(' ('+row['variant']+')') if row['variant'] else ''
    name=f'[{n}: {name}]({row["pr_url"]})'
    if row['pr_state']=='CLOSED':name+=' · CLOSED'
    head=f'[`{row["source"]["pr_head_sha"][:8]}`]({row["source"]["pinned_source_url"]})'
    o=row['official_result']
    off=f'#{o["rank"]}: **{fmt(o["users"])} users**;{fmt(o["requests_per_second"])} req/s;{fmt(o["p95_ms"])}/{fmt(o["p99_ms"])}ms' if o else 'No published score'
    if n==24:off+=';older `a38283c`,rerun queued'
    if row['official_unsuccessful_attempt']:off='No score: '+row['official_unsuccessful_attempt']
    self='; '.join(c['summary'].rstrip('.') for c in (row['self_reported_results'][:1] if n==2 else row['self_reported_results'])) or ('Correctness validation;load comparison underway.' if n==32 else 'No absolute performance claim found.')
    if n==11:self+='; follow-up holds are uncommitted source,not the pinned head.'
    if n in (8,31):self+='; 60-second screen, not a 5-minute hold.'
    if n in (29,30):self+='; duration/think scale unspecified.'
    short_protocol={1:'ARM Docker,8CPU,20s ramp+40s measured,×0.1',2:'Shared24-thread host,5min,×0.2',4:'Ryzen7700X,4c/8t,duration unspecified',5:'Dev seed,hold duration unspecified',7:'Same-host Xeon,8CPU/16GiB,5min',8:'GCP8vCPU/16GB,60s,newest bcrypt unmeasured',9:'Mac/dev seed,colocated generator',10:'i5 VM,4CPU,5min,×0.1',11:'Published head:4CPU/60s;follow-up:8CPU/300s',12:'ARM4CPU,nominal300s',13:'4CPU app/PG/generator,30s,×0.2',14:'Azure8vCPU/remote generator,5min',17:'Laptop/dev seed,duration unspecified',18:'Laptop/dev seed,duration unspecified',19:'DO4vCPU/8GB,remote generator,5min',20:'GCP8vCPU/16GB,5min',25:'Ryzen8threads,5min,×0.1;default-scale101k fails',26:'M2/full seed,duration unspecified',27:'8CPU/16GB,nginx extra2GB cap,60s',28:'8CPU/16GB,60s',29:'8CPU/full seed,duration and think scale unspecified',30:'8CPU/full seed,duration and think scale unspecified',31:'GCP8vCPU/16GB,60s,full seed'}.get(n)
    if short_protocol:self+=' ('+short_protocol+')'
    status={'PLANNED_NOT_YET_COMPARED':'Planned Rust control; not run','PLANNED_CORRECTED_REFERENCE_NOT_YET_COMPARED':'Corrected reference prepared; not run','SELF_ONLY_BATCHING_ABLATION_IN_PROGRESS':'Own ablation only','NOT_COMPARED':'Not compared','IN_PROGRESS_RESULT_PENDING':'In progress; result pending','CORRECTED_REFERENCE_CONFORMANCE_PASSED_NOT_COMPARED':'Corrected reference passed conformance; load comparison planned','OWN_ABLATION_ONLY_RUST_COMPARISON_IN_PROGRESS':'Own ablation; Rust comparison in progress'}[row['our_comparison']['status']]
    md.append('| '+ ' | '.join(map(clean,[name,head,off,self,status]))+' |')
md+=['','Official leaderboard notes remain material: #8 has a build/source caveat in the published table; #11 was scored with a PATH fix; #13 has a worker-restart-policy caveat (no restart occurred in the scored run); #2 was scored with a manually pinned bootstrap. Current PR changes may have addressed some issues;the old score alone does not validate the latest head.','', 'The original video examples report Go22,000,Java21,000,Rust19,000 and Python10,000users on different hardware. They are reference examples,not proof about the current optimized PR field.','', 'Coverage: all12current upstream submission folders map to a merged PR above. The two closed PRs are historical entries. D Vibe standard#17 and light#18 are separate variants despite sharing a folder name. New head/source pins,all numeric claims,protocol distinctions and source snapshot hashes are in `competitors.json`;raw README/PR/leaderboard snapshots are in `competitor-sources/`.']
text=tidy_prose('\n'.join(md)+'\n')
text=re.sub(r'(?<=\d)(?=ms\b)', ' ',text)
text=text.replace('records:16','records: 16').replace('contains17','contains 17').replace('remaining25','remaining 25').replace('all12','all 12').replace('standard#17','standard #17').replace('light#18','light #18')
# Small prose spacing cleanup; never changes embedded source URLs or SHA pins.
for a,b in [('16open','16 open'),('12merged','12 merged'),('2closed','2 closed'),('27active','27 active'),('17official','17 official'),('25active','25 active'),('dedicated8','dedicated 8'),('passing5','passing 5'),('all12current','all 12 current'),('Rust#7','Rust #7'),('Goose#31','Goose #31'),('tests,197','tests, 197'),('not5-minute','not a 5-minute'),('says135k','says 135k'),('Go22,000,Java21,000,Rust19,000','Go 22,000, Java 21,000, Rust 19,000'),('Python10,000users','Python 10,000 users')]:text=text.replace(a,b)
text=text.replace('Self-reported screens/holds are heterogeneous and are not sorted as a speed ranking.','Self-reported screens/holds are heterogeneous and are not sorted as a speed ranking. These claims have not been independently revalidated; absence of a result does not imply a slower implementation.')
(root/'competitors.md').write_text(text)
print(json.dumps(summary));print(root/'competitors.md')
