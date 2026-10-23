# Local capacity audit

Local shared ARM64 Mac/Docker capacity search; no official x86 rank or all-competitor claim.

Qualification follows the preregistered `dedicated_client_cgroup_v1` policy. Local and native qualification of each scored hold are shown separately.

| Implementation | Result |300s held users | Highest60s probe | p95/p99 ms | Measured errors | Local qualified | Native qualified | Whole-VM CPU flags |
|---|---|---:|---:|---:|---:|---|---|---:|
| rust7 | LOCAL_CAPACITY_INTERVAL | 130000 | 130000 | 117.951/580.095 | 0 | True | False | 7 |
| goose32-prototypeB | LOCAL_CAPACITY_INTERVAL | 140000 | 140000 | 18.015/307.711 | 0 | True | True | 0 |

Only a qualified300s hold yields a local held-user score. Ceiling/budget bounds are censored lower bounds, not proved maxima. Invalid generator/clock phases never become server failures or capacity scores. Native SLO permits<1% measured errors; zero errors and recorded ramp/tail errors are separate. This ARM Mac study cannot establish the official x86 leaderboard rank. Preregistered local qualification substitutes measured external-client cgroup CPU≤75% for the native whole-VM /proc/stat CPU flag only. All native timing/active-user gates remain. Native verdicts are preserved separately; a local score may remain native LG-limited and is not an official/native-qualified score.
