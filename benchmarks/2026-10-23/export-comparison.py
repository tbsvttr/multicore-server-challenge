#!/usr/bin/env python3
"""Export the verified published comparison; exclude downloaded sources and binaries."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('destination')
a = p.parse_args()
root = Path(__file__).resolve().parent
dest = Path(a.destination).resolve()
assert not dest.exists(), 'destination must be new'
assert root not in dest.parents, 'export outside the working tree'
assert (root / 'official-comparison.md').is_file()
dest.mkdir(parents=True)
manifest = {}
top = {'official-comparison.md', 'official-comparison.json', 'pr-body.md',
       'export-comparison.py'}
folders = {'inventory', 'audit', 'setup'}
for path in sorted(root.rglob('*')):
    if not path.is_file() or path.is_symlink():
        continue
    rel = path.relative_to(root)
    if len(rel.parts) == 1:
        if str(rel) not in top:
            continue
    elif rel.parts[0] not in folders or path.suffix not in {'.json', '.md', '.py'}:
        continue
    raw = path.read_bytes()
    raw.decode('utf-8')
    assert b'\0' not in raw, rel
    exported = Path('README.md') if str(rel) == 'official-comparison.md' else rel
    target = dest / exported
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    manifest[str(exported)] = {'source_relative_path': str(rel), 'bytes': len(raw),
                              'sha256': hashlib.sha256(raw).hexdigest()}
(dest / 'EXPORT-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'destination': str(dest), 'files': len(manifest),
                  'bytes': sum(row['bytes'] for row in manifest.values()),
                  'new_local_performance_runs': 0,
                  'result_origin': 'maintainer-published five-minute capacity scores'}))
