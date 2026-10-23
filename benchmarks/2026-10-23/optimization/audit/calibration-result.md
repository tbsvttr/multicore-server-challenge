# Five-arm80k calibration audit

PASS_EXPLORATORY_CALIBRATION

| Arm | Result | Req/s | p50/p95/p99 ms | CPU ms/success, full window | CPU ms/success, sampled inner | Errors |
|---|---|---:|---:|---:|---:|---:|
| rust7 | PASS | 21189.28 | 0.414/2.783/7.399 | 0.205379 | 0.205377 | 0 |
| share2r0 | PASS | 21188.50 | 0.973/2.863/5.503 | 0.178935 | 0.179008 | 0 |
| share2r1k | PASS | 21303.67 | 1.807/4.759/277.759 | 0.161241 | 0.161268 | 0 |
| share2r5k | PASS | 21178.08 | 3.081/5.611/6.771 | 0.151354 | 0.151254 | 0 |
| share1r6 | PASS | 21173.25 | 1.935/6.891/27.871 | 0.153875 | 0.153859 | 0 |

Selection: share2r5k

Each arm is one fixed-load run. CPU and latency contrasts are descriptive; similar closed-model request rates cannot establish sustainable capacity. No extra grid or selective reruns are authorized by this audit.
