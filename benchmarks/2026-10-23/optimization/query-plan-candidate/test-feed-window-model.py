#!/usr/bin/env python3
"""Check the bounded-window/fallback argument against the exact page contract.

This is an algorithm-model check, not execution of generated SQL. The parent
must still run actual SQL differential/API/concurrency/performance checks.
"""
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import random

root = Path(__file__).resolve().parent
rng = random.Random(20261023)
datasets = {
    'mixed_gapped_ids': [(i*3+1, rng.randrange(8)) for i in range(1800)],
    'older_only_followee': [(i*5+2, 0 if i<1100 else 1) for i in range(1800)],
    'empty': [],
    'tiny': [(9,0),(15,1),(80,0)],
}
counts = Counter()
checks = 0
for dataset, rows in datasets.items():
    newest = sorted(rows, reverse=True)
    for bits in range(256):
        followed = {i for i in range(8) if bits & (1<<i)}
        matching = [aid for aid,author in newest if author in followed]
        capped_count = min(len(matching), 1000)
        for limit,offset in itertools.product([0,1,5,10,100,101], [0,1,10,40,100,511,512,513,10000]):
            bound = limit+offset
            # This is the reference API/old SQL result for consistent parameters:
            # newest matching articles, the inner cap100, and outer limit.
            expected = matching[offset:offset+min(limit,100)]
            eligible = 1<=limit<=100 and offset>=0 and 1<=bound<=512 and capped_count>=bound
            window_size = min(512,max(128,4*bound)) if eligible else 0
            window = newest[:window_size]
            candidate = [aid for aid,author in window if author in followed][:bound]
            if eligible and len(candidate)==bound:
                got = candidate[offset:offset+limit]
                counts['fast_prefix'] += 1
            else:
                # The actual SQL fallback is the old indexed query. Independently
                # model those per-author scans rather than copy the direct oracle.
                per_author = []
                for author in followed:
                    per_author.extend([aid for aid,owner in newest if owner==author][:bound])
                got = sorted(per_author,reverse=True)[offset:offset+100][:limit]
                counts['indexed_fallback'] += 1
                if eligible and len(candidate)<bound:
                    counts['insufficient_recent_prefix'] += 1
            assert got==expected, (dataset,followed,limit,offset,got,expected)
            checks += 1
            if limit==0:
                counts['zero_limit'] += 1
            if offset>512:
                counts['deep_offset'] += 1
            if not matching:
                counts['empty_feed'] += 1
assert all(counts[k]>0 for k in ['fast_prefix','indexed_fallback','insufficient_recent_prefix',
                                'zero_limit','deep_offset','empty_feed'])
result = {'status':'PASS_ALGORITHM_MODEL_ONLY','checks':checks,'coverage':dict(counts),
          'dataset_names':list(datasets),'random_seed':20261023,
          'scope':'Pure deterministic model of exact prefix proof; no SQL/build/benchmark executed.',
          'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(root/'window-model-proof.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
