#!/usr/bin/env python3
"""Export completed optimization evidence without binaries or private state.

Never execute while a benchmark/audit writer is active. The source trees must
remain stable throughout the copy. Destination overwrite is refused. Original
audits are copied byte-for-byte, and pre-export binary checks are preserved in
a receipt because the public text bundle cannot rerun binary-presence checks.
"""
import argparse
import codecs
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

EXCLUDED_DIRS = {'.git','.agents','.codex','__pycache__','.build','.goose',
                 '.goose-home','.deps','bin','target','node_modules'}
PRIVATE_NAMES = {'STATE.json','STATE.md','AGENT_STATE.json','INTERNAL_STATE.json',
                 'INTERNAL_NOTES.md','AGENT_NOTES.md'}
RESERVED = {'EXPORT-MANIFEST.json','PREEXPORT-BINARY-AUDIT-RECEIPTS.json'}

def utc():
    return datetime.now(timezone.utc).isoformat()

def inside(path, root):
    return path == root or root in path.parents

def signature(path):
    s = path.lstat()
    return (s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def fingerprint(path):
    before = signature(path)
    h, size, nul, utf8, head = hashlib.sha256(),0,False,True,b''
    decoder = codecs.getincrementaldecoder('utf-8')('strict')
    with path.open('rb') as stream:
        while True:
            block = stream.read(1024*1024)
            if not block:
                break
            if not head:
                head = block[:4]
            h.update(block); size += len(block)
            nul = nul or b'\0' in block
            if utf8:
                try:
                    decoder.decode(block,final=False)
                except UnicodeDecodeError:
                    utf8 = False
        if utf8:
            try:
                decoder.decode(b'',final=True)
            except UnicodeDecodeError:
                utf8 = False
    if signature(path) != before:
        raise RuntimeError('source changed while hashing: '+str(path))
    return {'sha256':h.hexdigest(),'bytes':size,'has_nul':nul,
            'elf':head==b'\x7fELF','utf8':utf8,
            'posix_mode':oct(stat.S_IMODE(before[2])),'_signature':before}

def inventory(roots):
    found = {}
    def cannot_scan(error):
        raise error
    for label, root, prefix in roots:
        for base, dirs, files in os.walk(root,followlinks=False,onerror=cannot_scan):
            base = Path(base)
            symlink_dirs = [name for name in dirs if (base/name).is_symlink()]
            dirs[:] = [name for name in dirs if name not in symlink_dirs]
            for name in sorted(files+symlink_dirs):
                path = base/name
                relative = path.relative_to(root)
                logical = str(Path(prefix)/relative) if prefix else str(relative)
                if logical in found:
                    raise RuntimeError('duplicate export path: '+logical)
                found[logical] = {'path':path,'root':label,'relative':str(relative),
                                  'signature':signature(path)}
    return found

def capacity_receipt(audit_path, source_records):
    data = json.loads(audit_path.read_text())
    if not isinstance(data,dict) or not isinstance(data.get('raw_input_sha256'),dict) or not isinstance(data.get('run'),str) or not isinstance(data.get('rows'),list):
        return None
    run = Path(data['run']).resolve()
    binary_rows = []
    for row in data.get('rows',[]):
        if not isinstance(row,dict) or not isinstance(row.get('case'),str):
            continue
        name = row['case']
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',name):
            raise ValueError('unsafe case name in audit receipt')
        relative = 'cases/'+name+'/frozen/app'
        path = (run/relative).resolve()
        source = source_records.get(str(path))
        recorded = data['raw_input_sha256'].get(relative)
        expected = row.get('binary_sha256')
        exact_check = next((c.get('pass') for c in row.get('checks',[])
                            if c.get('check')=='exact_predeclared_case_and_binary'),None)
        actual = source.get('sha256') if source else None
        matched = bool(source and source.get('regular_file') and recorded
                       and recorded==actual==expected)
        binary_rows.append({'case':name,'source_run_relative_path':relative,
            'export_logical_path':source.get('logical_path') if source else None,
            'recorded_raw_input_sha256':recorded,'recorded_case_binary_sha256':expected,
            'actual_preexport_sha256':actual,'bytes':source.get('bytes') if source else None,
            'binary_present_before_export':bool(source and source.get('regular_file')),
            'hashes_match':matched,'original_auditor_binary_check':exact_check,
            'original_case_status':row.get('status')})
    source = source_records.get(str(audit_path.resolve()))
    if source is None:
        raise ValueError('audit receipt must be inside an admitted evidence tree')
    verified = bool(binary_rows) and all(r['hashes_match'] and r['original_auditor_binary_check'] is True for r in binary_rows)
    return {'original_audit_export_path':source['logical_path'],
            'original_audit_sha256':source['sha256'],'original_run':data['run'],
            'original_audit_created_utc':data.get('created_utc'),
            'original_audit_status':data.get('status'),
            'audit_performed_with_binaries_present':verified,
            'binary_witnesses':binary_rows,
            'interpretation':'Original audit is copied unmodified. Each verified witness below compares recorded binary hashes with a present original file before binary exclusion. Unverified witnesses remain explicitly unverified. This receipt is not a new capacity trial or a substitute for the original raw audit.'}

def export(args):
    root = args.source_root.resolve()
    history = args.historical_root.resolve()
    requested_dest = Path(os.path.abspath(args.destination))
    if requested_dest.exists() or requested_dest.is_symlink():
        raise FileExistsError('refusing to overwrite existing destination: '+str(requested_dest))
    dest = requested_dest.resolve()
    if not root.is_dir() or not history.is_dir():
        raise ValueError('source root and historical-profile root must exist')
    if inside(dest,root) or inside(root,dest):
        raise ValueError('destination must be separate from the live optimization tree')
    historical = sorted(p for p in history.glob('v3_multi_pair_20261023*') if p.is_dir() and not p.is_symlink())
    if len(historical)<4:
        raise ValueError('expected at least four preserved 23 October historical profiles; found '+str(len(historical)))
    roots = [('optimization',root,'')]+[(p.name,p,'historical-profiles/'+p.name) for p in historical]
    for _,source,_ in roots:
        if inside(dest,source) or inside(source,dest):
            raise ValueError('output/source recursion is forbidden')
    private = [Path(p) for p in args.exclude_internal]
    for path in private:
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('--exclude-internal paths must be relative to optimization root')
    initial = inventory(roots)
    dest.parent.mkdir(parents=True,exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.optimization-export-',dir=dest.parent))
    copied, excluded, source_records = {},{},{}
    try:
        for logical, item in sorted(initial.items()):
            path, relative = item['path'],Path(item['relative'])
            reasons = []
            banned = [part for part in relative.parts[:-1] if part in EXCLUDED_DIRS]
            if banned:
                reasons.append('excluded_directory:'+banned[0])
            if path.name in PRIVATE_NAMES:
                reasons.append('private_internal_state_or_notes')
            if item['root']=='optimization' and any(relative==p or p in relative.parents for p in private):
                reasons.append('explicit_private_internal_path')
            mode = path.lstat().st_mode
            entry = {'source_root':item['root'],'source_relative_path':item['relative'],
                     'logical_path':logical,'regular_file':stat.S_ISREG(mode)}
            if stat.S_ISLNK(mode):
                target = os.readlink(path)
                raw = target.encode('utf-8',errors='surrogateescape')
                entry.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
                             digest_kind='symlink_target_text',symlink_target=target)
                reasons.append('symlink_not_followed')
            elif not stat.S_ISREG(mode):
                raw = json.dumps({'mode':mode,'size':path.lstat().st_size},sort_keys=True).encode()
                entry.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),digest_kind='nonregular_metadata')
                reasons.append('nonregular_file_not_read')
            else:
                fp = fingerprint(path)
                entry.update({k:v for k,v in fp.items() if not k.startswith('_')})
                if fp['elf']:
                    reasons.append('elf_binary')
                if fp['has_nul']:
                    reasons.append('nul_containing_binary')
                if not fp['utf8']:
                    reasons.append('non_utf8_binary')
            # Do not resolve symlink entries into their targets: a link must not
            # overwrite the original regular-file witness used by an audit.
            if stat.S_ISREG(mode):
                key = str(path.resolve())
                if key in source_records:
                    raise ValueError('same source file admitted twice: '+key)
                source_records[key] = entry
            if reasons:
                excluded[logical] = dict(entry,reason=reasons[0],reasons=reasons)
                continue
            if logical in RESERVED:
                raise ValueError('source collides with generated metadata: '+logical)
            output = stage/logical
            output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,output,follow_symlinks=False)
            copied_fp = fingerprint(output)
            if copied_fp['sha256']!=entry['sha256'] or copied_fp['bytes']!=entry['bytes']:
                raise RuntimeError('copy checksum mismatch: '+logical)
            copied[logical] = entry
        # Explicit receipt paths are preferred. Otherwise discover only audit-
        # named JSON files, avoiding large raw histograms and protocol dumps.
        paths = [Path(p).resolve() for p in args.preexport_audit]
        explicit = bool(paths)
        if not paths:
            paths = [item['path'] for logical,item in initial.items() if logical in copied
                     and item['path'].suffix=='.json'
                     and ('audit' in item['path'].name.lower() or 'audit' in Path(item['relative']).parts[:-1])]
        receipts = []
        for path in sorted(set(paths)):
            try:
                receipt = capacity_receipt(path,source_records)
            except json.JSONDecodeError:
                if explicit:
                    raise
                # An old failed/non-JSON audit artifact is still exported as
                # text. It is not silently promoted to a verified receipt.
                continue
            if receipt:
                if receipt['original_audit_export_path'] not in copied:
                    raise ValueError('original capacity audit must be copied unchanged into export: '+str(path))
                receipts.append(receipt)
            elif explicit:
                raise ValueError('not an original capacity audit receipt: '+str(path))
        if explicit and not all(r['audit_performed_with_binaries_present'] for r in receipts):
            raise ValueError('explicit capacity audit has no matching present binary receipts')
        has_capacity = any(p.is_dir() for p in root.glob('capacity_*'))
        if has_capacity and not any(r['audit_performed_with_binaries_present'] for r in receipts):
            raise ValueError('capacity evidence needs a completed original audit with binary hashes; use --preexport-audit PATH')
        # Detect additions/removals as well as changes during hashing/copying.
        final = inventory(roots)
        if set(initial)!=set(final) or any(initial[k]['signature']!=final[k]['signature'] for k in initial):
            raise RuntimeError('source evidence changed during export; no destination published')
        receipt_obj = {'schema':'preexport-capacity-binary-audit-receipts-v1',
            'created_utc':utc(),'receipts':receipts,
            'context':'Verified receipts identify capacity audits whose recorded binary checks match original frozen executables present at export. Original audit artifacts are retained byte-for-byte, including failed or unverified records. ELF/NUL binaries are omitted only from this public text export; their actual pre-export SHA-256 values and exclusion reasons remain in EXPORT-MANIFEST.json.',
            'verified_preexport_capacity_audits':sum(r['audit_performed_with_binaries_present'] for r in receipts)}
        receipt_path = stage/'PREEXPORT-BINARY-AUDIT-RECEIPTS.json'
        receipt_path.write_text(json.dumps(receipt_obj,indent=2)+'\n')
        receipt_fp = fingerprint(receipt_path)
        manifest = {'schema':'multicore-optimization-text-export-v1','created_utc':utc(),
            'source_roots':[{'label':label,'host_path':str(source),'export_prefix':prefix} for label,source,prefix in roots],
            'historical_profiles_count':len(historical),
            'copied_files':copied,'excluded_files':excluded,
            'generated_files':{'PREEXPORT-BINARY-AUDIT-RECEIPTS.json':{k:v for k,v in receipt_fp.items() if not k.startswith('_')}},
            'counts':{'copied_files':len(copied),'excluded_files':len(excluded),
                      'copied_bytes':sum(r['bytes'] for r in copied.values()),
                      'excluded_bytes':sum(r['bytes'] for r in excluded.values())},
            'policy':{'excluded_directory_components':sorted(EXCLUDED_DIRS),
                      'private_basenames':sorted(PRIVATE_NAMES),
                      'explicit_private_paths':[str(p) for p in private],
                      'binaries_not_exported':True,'source_content_rewritten':False,
                      'source_stability_verified':True,'destination_overwrite_allowed':False,
                      'symlink_targets_not_traversed':True,
                      'digest_note':'Regular-file hashes cover complete original bytes. Symlink hashes cover their link text; nonregular-file hashes cover recorded metadata. Every excluded regular file is still hashed, including files inside generated directories and frozen app executables.'}}
        (stage/'EXPORT-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if dest.exists() or dest.is_symlink():
            raise FileExistsError('destination appeared during export; refusing replacement')
        stage.rename(dest)
        return {'destination':str(dest),**manifest['counts'],
                'historical_profiles':len(historical),
                'verified_preexport_capacity_audits':receipt_obj['verified_preexport_capacity_audits']}
    finally:
        if stage.exists():
            shutil.rmtree(stage)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('destination',nargs='?',type=Path,
        default=Path('/private/tmp/multicore-evidence-20261022/benchmarks/2026-10-23/optimization'))
    p.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--historical-root',type=Path,
        default=Path('/private/tmp/multicore-research-20261022/paired-multi-load-v3'))
    p.add_argument('--preexport-audit',action='append',default=[],metavar='PATH',
        help='original completed capacity audit with raw_input_sha256; repeatable')
    p.add_argument('--exclude-internal',action='append',default=[],metavar='RELATIVE_PATH',
        help='additional private agent-state/message path; benchmark/review notes otherwise remain')
    args = p.parse_args()
    print(json.dumps(export(args)))

if __name__=='__main__':
    main()
