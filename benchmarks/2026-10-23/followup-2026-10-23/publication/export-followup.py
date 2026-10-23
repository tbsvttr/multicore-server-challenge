#!/usr/bin/env python3
"""Append a text evidence checkpoint; preserve the earlier export and all raw bytes."""
from pathlib import Path
import hashlib,json,shutil,datetime
ROOT=Path('/private/tmp/multicore-optimize-20261023').resolve()
DEST=Path('/private/tmp/multicore-evidence-20261022/benchmarks/2026-10-23/followup-2026-10-23')
PREFIXES=[
 'diagnosticgoose110p2_20261023t181051_2b1bad',
 'builds/reader_admission_20261023t181010_2fa4e2',
 'capacity-v4','ci/leader2-executed','diagnostics/native-darwin-plan',
 'capacity_20261023t192322_84394f','candidates/leader2-ready',
 'capacity-confirmation-v1','confirmation_20261023t211121_c42d47',
 'publication/new-unscored-34-42','publication/latest-official-during-confirmation',
 'publication/latest-official-after-p2',
]
FILES=[
 'diagnostics/run-with-power-guard.py','diagnostics/power-guard-p2-20261023t1811.jsonl',
 'diagnostics/goose110-gc-pg-p2/plan-powered-20261023t1809.json',
 'diagnostics/goose110-gc-pg-p2/plan-powered-20261023t1809.json.sha256',
 'audit/diagnostic-p2-review.json','audit/diagnostic-p2-review.md','audit/diagnostic-p2-review.py',
 'audit/host-top-p2-20261023t1818.txt','audit/power-block-cleanup-after-p2.json',
 'ci/pr-body-evidence-checkpoint.md','publication/pr-evidence-update-receipt.json',
 'publication/export-followup.py','publication/followup-README.md','publication/followup-result-summary.json',
 'profiles/capacity-v4-sourceB-config.json','profiles/capacity-v4-sourceB-plan.json','profiles/capacity-v4-sourceB-plan.json.sha256',
 'profiles/power-guard-capacity-v4-20261023t1901.jsonl',
 'audit/leader2-ready-source-transfer.json','audit/capacity-v4-frozen-input-review.json','audit/capacity-v4-frozen-input-review.md',
 'audit/capacity-v4-result.json','audit/capacity-v4-result.md','audit/confirmation-v1-result.json','audit/confirmation-v1-result.md',
 'profiles/capacity-confirmation-v1-selected-config.json','profiles/capacity-confirmation-v1-selected-plan.json','profiles/capacity-confirmation-v1-selected-plan.json.sha256',
 'profiles/power-guard-confirmation-v1-20261023.jsonl','profiles/power-guard-confirmation-v1-finishing-charge-20261023.jsonl',
 'diagnostics/run-with-power-guard-v2.py','audit/final-benchmark-resource-cleanup.json',
 'publication/promoted-code-equivalence.json','publication/promoted-source-receipt.json',
 'publication/promotion-README-FINAL.md','publication/pr-body-reader-bounds-FINAL.md',
 'audit/capacity-first-result.json','audit/capacity-v2-result.json','audit/capacity-v3-result.json',
 'audit/capacity-powered-result.json','audit/capacity-rust110-115-result.json','audit/final-source-100k-comparison.json',
 'publication/followup-result-summary.pre-promotion.json','publication/followup-result-summary.before-correctness-validation.json',
 'publication/promoted-source-receipt.pre-publication-status.json',
]

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 assert not DEST.exists(),'refuse overwrite of an earlier checkpoint'
 files=[]
 for prefix in PREFIXES:
  p=ROOT/prefix
  assert p.is_dir(),str(p)
  files.extend(x for x in p.rglob('*') if x.is_file())
 files.extend(ROOT/f for f in FILES)
 for pattern in ['audit/capacity-v4-*-review.*','audit/rust-v4-session-independent.*','audit/confirmation-v1-*-review.*','audit/confirmation-v1-*-replay.*','publication/final-current-table-*','publication/current-table-*','publication/final-docs-*']:
  files.extend(p for p in ROOT.glob(pattern) if p.is_file())
 files=sorted(set(files))
 selected=[];omitted=[]
 for p in files:
  rel=p.relative_to(ROOT)
  if any(x in {'__pycache__','go-build-cache','go-mod-cache','.git'} for x in rel.parts) or p.name=='.DS_Store':continue
  assert not p.is_symlink(),'symlink requires explicit review: '+str(p)
  with p.open('rb') as stream:magic=stream.read(4)
  reason=None
  if str(rel)=='diagnostics/native-darwin-plan/native10k-20261023t1852/backend-pids.log':reason='Incidental unrelated host process discovery list retained privately; exact hash and backend-only public replacement retained'
  elif magic==b'\x7fELF' or magic in (b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf'):reason='executable binary omitted; exact hash retained'
  elif magic[:2]==b'PK' or magic[:2]==b'\x1f\x8b' or p.suffix in {'.zip','.gz','.pyc'}:reason='archive/cache binary omitted; text extraction and exact hash retained'
  item={'path':str(rel),'bytes':p.stat().st_size,'sha256':sha(p)}
  if reason:omitted.append(dict(item,reason=reason))
  else:
   p.read_text(encoding='utf-8')
   selected.append((p,item))
 expected={'diagnostics/native-darwin-plan/loadgen-darwin':'c6053653c26c2136bd7bd007df68cfb8cf51975f9bf8e6f38bcebdd7484076e9'}
 binary_checks=[]
 for p,item in selected:
  if p.name!='metadata.json' or p.parent.name not in {'frozen','server-frozen'}:continue
  x=json.loads(p.read_text())
  if not (x.get('binary_sha256') and x.get('frozen_binary')):continue
  s=x['frozen_binary']
  if not s.startswith('/comparison/optimization/'):continue
  rel=s.removeprefix('/comparison/optimization/')
  expected[rel]=x['binary_sha256']
 for rel,digest in expected.items():
  p=ROOT/rel;actual=sha(p)
  assert actual==digest,(rel,actual,digest)
  binary_checks.append({'path':rel,'expected_sha256':digest,'actual_sha256':actual,'pass':True})
 DEST.mkdir(parents=True)
 for p,item in selected:
  out=DEST/item['path'];out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
  assert sha(out)==item['sha256']
 for source,name in [('publication/followup-README.md','README.md'),('publication/followup-result-summary.json','result-summary.json')]:
  p=ROOT/source;shutil.copy2(p,DEST/name)
  selected.append((p,{'path':name,'source_path':source,'bytes':p.stat().st_size,'sha256':sha(p)}))
 manifest={'schema':'multicore-followup-text-export-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Incremental append-only evidence. Existing optimization export/raw attempts remain unchanged. Original absolute runtime paths describe the original workspace; this text bundle is not a standalone binary replay.','prior_export_commit':'dd941e3285933eee82d7a9da4433ec18701032a9','copied':[x for _,x in selected],'omitted':omitted,'original_frozen_binary_preexport_checks':binary_checks,'excluded_cache_directory_names':['__pycache__','go-build-cache','go-mod-cache','.git'],'private_STATE_excluded':True,'native_or_official_score_created':False}
 (DEST/'EXPORT-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'destination':str(DEST),'copied':len(selected),'bytes':sum(x['bytes'] for _,x in selected),'omitted':len(omitted),'binary_checks':len(binary_checks)}))
if __name__=='__main__':main()
