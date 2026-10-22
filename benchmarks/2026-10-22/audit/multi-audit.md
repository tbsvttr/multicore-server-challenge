# Independent 80k four-shard audit

Saved local ARM64 Mac/Docker diagnostics; official rank and capacity are unproven.
Native SLO PASS permits fewer than 1% measured errors. Measured and full recorded timeline errors are listed separately; errorful pairs cannot enter clean performance aggregation.

## multi_pair_20261022t190313_9c13b1

Status: **INVALID_TARGET_NOFILE**

| Attempt | Result | Measured errors | Timeline errors | Req/s | p95/p99 ms | Total CPU ms/success |
|---|---|---:|---:|---:|---:|---:|
| 01-p1-rust7 | INVALID_TARGET_NOFILE | 350029 | 581936 | 6103.7333 | 10002.4310/10010.6230 | 0.3857 |
| 02-p1-goose | INCOMPLETE | unverified | unverified | unverified | unverified/unverified | unverified |

Four native histograms are verified by exact bin sum. At fixed closed-model load, similar request rates do not establish equal capacity; lower latency or CPU per success is diagnostic only. No warmup/search/5min hold, official x86 score, or ranking proof.

Pair 1: no clean performance comparison; all attempts retained. 

Pair 2: no clean performance comparison; all attempts retained. 

Pair 3: no clean performance comparison; all attempts retained. 

## v2_multi_pair_20261022t192010_1e24f0

Status: **HAS_INVALID_OR_FAILED_ATTEMPTS**

| Attempt | Result | Measured errors | Timeline errors | Req/s | p95/p99 ms | Total CPU ms/success |
|---|---|---:|---:|---:|---:|---:|
| 01-p1-rust7 | INVALID_GENERATOR | 0 | 0 | 20674.7833 | 831.9990/2408.4470 | 0.2137 |
| 02-p1-goose | INVALID_GENERATOR_CGROUP | 21046 | 32842 | 15384.5333 | 9715.7110/13606.9110 | 0.2422 |
| 03-p2-goose | INCOMPLETE | unverified | unverified | unverified | unverified/unverified | unverified |

Four native histograms are verified by exact bin sum. At fixed closed-model load, similar request rates do not establish equal capacity; lower latency or CPU per success is diagnostic only. No warmup/search/5min hold, official x86 score, or ranking proof.

Pair 1: no clean performance comparison; all attempts retained. 

Pair 2: no clean performance comparison; all attempts retained. 

Pair 3: no clean performance comparison; all attempts retained. 

