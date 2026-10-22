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

## v3_multi_pair_20261022t193438_99f820

Status: **HAS_INVALID_OR_FAILED_ATTEMPTS**

| Attempt | Result | Measured errors | Timeline errors | Req/s | p95/p99 ms | Total CPU ms/success |
|---|---|---:|---:|---:|---:|---:|
| 01-p1-rust7 | PASS | 0 | 0 | 21163.7167 | 3.0010/97.5350 | 0.2097 |
| 02-p1-goose | PASS | 0 | 0 | 21088.4667 | 55.2630/395.5190 | 0.2238 |
| 03-p2-goose | INVALID_GENERATOR | 0 | 0 | 0.0000 | 0.0000/0.0000 | unverified |
| 04-p2-rust7 | PASS | 0 | 0 | 21216.3000 | 4.9830/53.9830 | 0.2208 |
| 05-p3-rust7 | PASS | 0 | 0 | 21149.3833 | 3.1150/5.6550 | 0.2186 |
| 06-p3-goose | PASS | 0 | 0 | 21152.0333 | 1.3430/2.9510 | 0.2169 |

Four native histograms are verified by exact bin sum. At fixed closed-model load, similar request rates do not establish equal capacity; lower latency or CPU per success is diagnostic only. No warmup/search/5min hold, official x86 score, or ranking proof.

Pair 1, goose/rust7 change: RPS -0.356%; p95 +1741.486%; p99 +305.515%; total CPU/success +6.706%.

Pair 2: no clean performance comparison; all attempts retained. 

Pair 3, goose/rust7 change: RPS +0.013%; p95 -56.886%; p99 -47.816%; total CPU/success -0.760%.

