#!/usr/bin/env python3
"""Copy text evidence to an empty directory; exclude binaries and generated seeds."""
import argparse
import hashlib
import json
import pathlib
import shutil

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('destination')
a = p.parse_args()
root = pathlib.Path(__file__).resolve().parent
dest = pathlib.Path(a.destination).resolve()
assert not dest.exists(), 'destination must be new'
assert root not in dest.parents, 'export outside the live evidence tree'
dest.mkdir(parents=True)
extensions = {'.json', '.jsonl', '.txt', '.log', '.md', '.py', '.sh', '.c', '.h',
              '.goose', '.yml', '.patch', '.sql', '.go', '.mod', '.sum', '.toml', '.lock'}
subtrees = {'audit', 'baseline', 'box', 'conformance', 'fork-ci', 'native-checks',
            'paired-load', 'paired-multi-load', 'paired-multi-load-v2',
            'paired-multi-load-v3',
            'pr31-reference', 'setup',
            'competitor-sources', 'nofile-v2', 'diagnostics',
            'proposed-w2-article1-v3', 'proposed-pr31-w2-article1-v3'}
skip = {'.git', '.build', '.goose', '.goose-home', '.deps', 'bin', 'target',
        '__pycache__', 'node_modules'}
manifest = {}
for path in sorted(root.rglob('*')):
    if not path.is_file() or path.is_symlink():
        continue
    rel = path.relative_to(root)
    if any(part in skip for part in rel.parts):
        continue
    if len(rel.parts) > 1 and rel.parts[0] not in subtrees:
        if str(rel) not in {'clean-build/build.log', 'clean-build/source-sha256.json'}:
            continue
    if len(rel.parts) == 1 and path.suffix not in extensions:
        continue
    data = path.read_bytes()
    if b'\0' in data[:8192]:
        continue
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        continue
    exported_rel = rel
    if str(rel) == 'README.md':
        exported_rel = pathlib.Path('UPSTREAM-README.md')
    elif str(rel) == 'local-results.md':
        exported_rel = pathlib.Path('README.md')
    target = dest / exported_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    manifest[str(exported_rel)] = {'source_relative_path': str(rel), 'bytes': len(data),
                                 'sha256': hashlib.sha256(data).hexdigest()}
(dest / 'EXPORT-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'destination': str(dest), 'files': len(manifest),
                  'bytes': sum(r['bytes'] for r in manifest.values())}))
