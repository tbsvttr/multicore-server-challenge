#!/usr/bin/env python3
"""Tiny synthetic-only preservation tests; never opens actual capacity files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SCRIPT = Path(__file__).resolve().parents[1] / 'export-optimization.py'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def snapshot(root):
    result = {}
    for base, dirs, files in os.walk(root,followlinks=False):
        base = Path(base)
        links = [n for n in dirs if (base/n).is_symlink()]
        dirs[:] = [n for n in dirs if n not in links]
        for name in files+links:
            path = base/name
            result[str(path.relative_to(root))] = (os.readlink(path) if path.is_symlink()
                else sha(path.read_bytes()))
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path)
    args = parser.parse_args()
    checks = []
    def check(name,condition):
        checks.append({'check':name,'pass':bool(condition)})
        if not condition:
            raise AssertionError(name)

    with tempfile.TemporaryDirectory(prefix='optimization-export-synthetic-',dir='/private/tmp') as tmp:
        work = Path(tmp)
        source, history, dest = work/'source',work/'history',work/'public'/'optimization'
        source.mkdir(); history.mkdir()
        def write(path,data):
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data if isinstance(data,bytes) else data.encode())

        write(source/'server.goose','// exact source\n')
        write(source/'runtime-candidate-notes.md','Benchmark findings retained.\n')
        write(source/'STATE.json','{"internal_state":"private"}\n')
        write(source/'internal/messages.json','{"private_message":"omit"}\n')
        write(source/'archive/failed-original.json.orig','{"status":"FAIL","errors":12}\n')
        write(source/'audit/old-failed-audit.json','An intentionally incomplete old audit.\n')
        write(source/'.build/generated.c','/* excluded generated source, still hashed */\n')
        write(source/'candidates/old/.goose/library.goose','// excluded dependency\n')
        write(source/'bin/old-app',b'\x7fELF\x00old binary')
        write(source/'invalid-utf8.dat',b'\xff\xfe')
        write(source/'nul.dat',b'text\x00tail')
        run = source/'capacity_synthetic'
        binaries = {'goose':b'\x7fELF\x00goose frozen','rust':b'\x7fELF\x00rust frozen'}
        rows, raw = [],{}
        for case, data in binaries.items():
            rel = 'cases/'+case+'/frozen/app'
            write(run/rel,data)
            write(run/('cases/'+case+'/frozen/source/routes.goose'),'// frozen '+case+'\n')
            raw[rel] = sha(data)
            rows.append({'case':case,'status':'SYNTHETIC_ONLY',
                         'binary_sha256':sha(data),
                         'checks':[{'check':'exact_predeclared_case_and_binary','pass':True}]})
        audit = source/'audit/final-capacity.json'
        write(audit,json.dumps({'run':str(run),'status':'SYNTHETIC_ONLY',
                               'rows':rows,'raw_input_sha256':raw},indent=2)+'\n')
        (source/'zz-app-link').symlink_to('capacity_synthetic/cases/goose/frozen/app')
        (source/'symlink-directory').symlink_to('archive',target_is_directory=True)
        (source/'dangling-link').symlink_to('does-not-exist')
        for index in range(4):
            old = history/('v3_multi_pair_20261023t00000'+str(index)+'_synthetic')
            write(old/'raw.json','{"historical_arm":'+str(index)+',"status":"FAIL"}\n')
            write(old/'raw.json.orig','prior failed record '+str(index)+'\n')
        before = snapshot(source),snapshot(history)
        common = [sys.executable,str(SCRIPT),'--source-root',str(source),
                  '--historical-root',str(history),'--exclude-internal','internal']
        def invoke(destination,*options):
            return subprocess.run(common+list(options)+[str(destination)],
                                  text=True,capture_output=True)
        result = invoke(dest,'--preexport-audit',str(audit))
        check('completed_synthetic_export',result.returncode==0)
        manifest = json.loads((dest/'EXPORT-MANIFEST.json').read_text())
        receipt = json.loads((dest/'PREEXPORT-BINARY-AUDIT-RECEIPTS.json').read_text())
        copied, excluded = manifest['copied_files'],manifest['excluded_files']
        check('all_four_historical_runs_preserved',manifest['historical_profiles_count']==4
              and len([p for p in copied if p.startswith('historical-profiles/')])==8)
        check('failed_and_orig_artifacts_unchanged',
              (dest/'archive/failed-original.json.orig').read_bytes()==(source/'archive/failed-original.json.orig').read_bytes()
              and (dest/'audit/old-failed-audit.json').read_bytes()==(source/'audit/old-failed-audit.json').read_bytes())
        check('benchmark_notes_preserved','runtime-candidate-notes.md' in copied)
        check('private_state_and_messages_not_copied','STATE.json' in excluded
              and 'internal/messages.json' in excluded and not (dest/'STATE.json').exists()
              and not (dest/'internal/messages.json').exists())
        check('generated_text_hashed_but_excluded','.build/generated.c' in excluded
              and 'excluded_directory:.build' in excluded['.build/generated.c']['reasons'])
        check('all_excluded_paths_have_hash_and_reason',all(
              len(item['sha256'])==64 and item['reasons'] for item in excluded.values()))
        check('all_copied_paths_match_original_sha_and_bytes',all(
              sha((dest/path).read_bytes())==item['sha256'] and (dest/path).stat().st_size==item['bytes']
              for path,item in copied.items()))
        for case,data in binaries.items():
            rel = 'capacity_synthetic/cases/'+case+'/frozen/app'
            check('frozen_'+case+'_binary_excluded_with_complete_hash',
                  rel in excluded and excluded[rel]['sha256']==sha(data)
                  and not (dest/rel).exists() and 'elf_binary' in excluded[rel]['reasons'])
        check('non_utf8_and_nul_binaries_excluded',
              'non_utf8_binary' in excluded['invalid-utf8.dat']['reasons']
              and 'nul_containing_binary' in excluded['nul.dat']['reasons'])
        check('symlinks_not_followed',all(p in excluded for p in
              ['zz-app-link','symlink-directory','dangling-link'])
              and not (dest/'symlink-directory').exists())
        check('symlink_digest_is_link_text',excluded['zz-app-link']['sha256']==sha(
              b'capacity_synthetic/cases/goose/frozen/app'))
        check('symlink_cannot_overwrite_original_binary_receipt',
              receipt['verified_preexport_capacity_audits']==1
              and len(receipt['receipts'][0]['binary_witnesses'])==2
              and all(r['hashes_match'] and r['binary_present_before_export']
                      for r in receipt['receipts'][0]['binary_witnesses']))
        check('original_capacity_audit_copied_unchanged',(dest/'audit/final-capacity.json').read_bytes()==audit.read_bytes())
        check('generated_receipt_hash_recorded',sha((dest/'PREEXPORT-BINARY-AUDIT-RECEIPTS.json').read_bytes())==
              manifest['generated_files']['PREEXPORT-BINARY-AUDIT-RECEIPTS.json']['sha256'])
        check('source_and_historical_trees_unchanged',before==(snapshot(source),snapshot(history)))
        published = snapshot(dest)
        again = invoke(dest,'--preexport-audit',str(audit))
        check('existing_destination_refused_without_mutation',again.returncode!=0
              and 'refusing to overwrite' in again.stderr and snapshot(dest)==published)
        dangling_dest = work/'dangling-destination'
        dangling_dest.symlink_to('nonexistent-destination')
        dangling = invoke(dangling_dest,'--preexport-audit',str(audit))
        check('dangling_destination_symlink_refused',dangling.returncode!=0
              and dangling_dest.is_symlink() and not (work/'nonexistent-destination').exists())
        auto_dest = work/'auto-receipt-export'
        auto = invoke(auto_dest)
        check('auto_discovers_receipt_and_preserves_malformed_failed_audit',auto.returncode==0
              and json.loads((auto_dest/'PREEXPORT-BINARY-AUDIT-RECEIPTS.json').read_text())['verified_preexport_capacity_audits']==1
              and (auto_dest/'audit/old-failed-audit.json').exists())
        original_audit = audit.read_bytes()
        bad = json.loads(original_audit)
        bad['rows'][0]['binary_sha256'] = '0'*64
        write(audit,json.dumps(bad))
        bad_dest = work/'bad-receipt-export'
        mismatch = invoke(bad_dest,'--preexport-audit',str(audit))
        check('mismatched_original_binary_receipt_blocks_publication',mismatch.returncode!=0
              and 'no matching present binary receipts' in mismatch.stderr and not bad_dest.exists())
        audit.write_bytes(original_audit)
        recursive = invoke(source/'nested-output','--preexport-audit',str(audit))
        check('output_self_recursion_refused',recursive.returncode!=0
              and not (source/'nested-output').exists())

        # Load functions without import bytecode or actual source-tree scanning.
        module = {'__name__':'export_synthetic_test','__file__':str(SCRIPT)}
        exec(compile(SCRIPT.read_text(),str(SCRIPT),'exec'),module)
        original_copy = shutil.copy2
        injected = [False]
        def inject_change(*args,**kwargs):
            value = original_copy(*args,**kwargs)
            if not injected[0]:
                write(source/'late-source-addition.txt','simulated active writer\n')
                injected[0] = True
            return value
        changed_dest = work/'changed-source-export'
        namespace = argparse.Namespace(source_root=source,historical_root=history,
                                       destination=changed_dest,preexport_audit=[str(audit)],
                                       exclude_internal=['internal'])
        shutil.copy2 = inject_change
        changed_error = None
        try:
            module['export'](namespace)
        except RuntimeError as error:
            changed_error = str(error)
        finally:
            shutil.copy2 = original_copy
        check('source_addition_during_export_blocks_publication',changed_error is not None
              and 'source evidence changed' in changed_error and not changed_dest.exists())
        check('all_failed_staging_directories_cleaned',not list(work.rglob('.optimization-export-*')))
        check('synthetic_checks_only',str(source).startswith('/private/tmp/optimization-export-synthetic-'))

    proof = {'status':'PASS','scope':'Tiny synthetic files only; no real capacity raw evidence opened.',
             'exporter_sha256':sha(SCRIPT.read_bytes()),'checks':checks,
             'passed':len(checks),'failed':0}
    if args.out:
        args.out.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'status':proof['status'],'passed':len(checks),'failed':0}))

if __name__=='__main__':
    main()
