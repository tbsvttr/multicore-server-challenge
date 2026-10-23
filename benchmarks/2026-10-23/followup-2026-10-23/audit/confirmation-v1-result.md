# Selected-point confirmation audit

Fresh reverse-order confirmation of selected held points only; no capacity maximum, official x86 rank or causal claim.

Qualification follows the preregistered `dedicated_client_cgroup_v1` policy. Local and native qualification of each scored hold are shown separately.

| Implementation | Result | Selected users | Confirmed300s users | p95/p99 ms | Measured errors | Local qualified | Native qualified | Whole-VM CPU flags |
|---|---|---:|---:|---:|---:|---|---|---:|
| goose32-prototypeB | LOCAL_CONFIRMATION_PASSED | 140000 | 140000 | 10.903/239.615 | 0 | True | True | 0 |
| rust7 | LOCAL_CONFIRMATION_PASSED | 130000 | 130000 | 24.783/401.407 | 0 | True | False | 7 |

This fresh reverse-order block confirms only its preselected held-user points when warmup, probe and300s hold all qualify. It does not search for or establish a new maximum or failure bound; prior first-study bounds remain separate. Any invalidity or SLO failure stops that case without fallback, retry or phase reuse. Native flags and exact measured/ramp/tail errors remain visible. No official x86 rank or controlled causal claim is made. The unchanged preregistered local policy substitutes external-client cgroup CPU<=75% for native whole-VM CPU only. All timing/active/clock/histogram/error/SLO gates remain; local confirmation can remain native LG-limited.
