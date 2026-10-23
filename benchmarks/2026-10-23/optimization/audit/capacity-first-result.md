# Local capacity audit

Local shared ARM64 Mac/Docker capacity search; no official x86 rank or all-competitor claim.

| Implementation | Result |300s held users | Highest60s probe | p95/p99 ms | Measured errors |
|---|---|---:|---:|---:|---:|
| rust7 | INVALID_GENERATOR | — | 80000 | —/— | — |
| goose32 | INCOMPLETE | — | — | —/— | — |

Only a qualified300s hold yields a local held-user score. Ceiling/budget bounds are censored lower bounds, not proved maxima. Invalid generator/clock phases never become server failures or capacity scores. Native SLO permits<1% measured errors; zero errors and recorded ramp/tail errors are separate. This ARM Mac study cannot establish the official x86 leaderboard rank.
