#!/usr/bin/env python3
import concurrent.futures, json, pathlib, subprocess, tarfile, hashlib, datetime
root=pathlib.Path('/private/tmp/multicore-comparison-20261023');inv=root/'inventory';sources=root/'sources'
prs=json.loads((inv/'pulls-raw.json').read_text());old=json.loads(pathlib.Path('/private/tmp/multicore-research-20261022/competitors.json').read_text());folders={c['pr']:c['implementation'] for c in old['competitors']}
(inv/'head-trees').mkdir(exist_ok=True)
def fetch(pr):
 n=pr['number'];sha=pr['head']['sha'];repo=(pr['head']['repo'] or {}).get('full_name') or 'arjaythedev/multicore-server-challenge';entry={'pr':n,'head':sha,'head_repository':repo,'folder':folders[n]}
 treefile=inv/'head-trees'/f'pr-{n}-{sha[:8]}.json'
 r=subprocess.run(['gh','api',f'repos/{repo}/git/trees/{sha}?recursive=1'],capture_output=True)
 if r.returncode and repo!='arjaythedev/multicore-server-challenge':
  repo='arjaythedev/multicore-server-challenge';r=subprocess.run(['gh','api',f'repos/{repo}/git/trees/{sha}?recursive=1'],capture_output=True)
 entry['tree_api_repository']=repo
 if r.returncode:entry['tree_error']=r.stderr.decode();return entry
 treefile.write_bytes(r.stdout);tree=json.loads(r.stdout);entry['root_tree_sha']=tree['sha'];entry['tree_file']=str(treefile);entry['tree_truncated']=tree.get('truncated',False)
 target='submissions/'+folders[n];folder=[x for x in tree['tree'] if x['path']==target and x['type']=='tree'];entry['submission_tree_sha']=folder[0]['sha'] if folder else None
 entry['script_paths']=[x['path'] for x in tree['tree'] if x['path'].startswith(target+'/') and x['path'].count('/')==2 and x['path'].split('/')[-1] in ['install.sh','build.sh','start.sh','README.md']]
 if not pr['merged_at']:
  archive=sources/f'pr-{n}-{sha[:8]}.tar.gz'
  with archive.open('wb') as f:r=subprocess.run(['gh','api',f'repos/{repo}/tarball/{sha}'],stdout=f,stderr=subprocess.PIPE)
  if r.returncode:entry['archive_error']=r.stderr.decode();return entry
  entry['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest();dest=sources/f'pr-{n}-{sha[:8]}'
  dest.mkdir(exist_ok=False)
  with tarfile.open(archive) as tar:
   allmembers=tar.getmembers();prefix=allmembers[0].name.split('/')[0]+'/'+target
   members=[m for m in allmembers if m.name==prefix or m.name.startswith(prefix+'/')]
   if not members:entry['extraction_error']='submission folder absent';return entry
   tar.extractall(dest,members=members,filter='data')
  extracted=list(dest.iterdir());assert len(extracted)==1
  entry['source_dir']=str(extracted[0]/target)
 return entry
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 entries=list(pool.map(fetch,sorted(prs,key=lambda p:p['number'])))
result={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'entries':entries,'scope':'Public GitHub read-only snapshots only; no install, build or execution.'}
(inv/'head-source-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
for e in entries:print(e['pr'],e.get('submission_tree_sha'),e.get('source_dir'),e.get('tree_error',e.get('archive_error',e.get('extraction_error','OK'))))
