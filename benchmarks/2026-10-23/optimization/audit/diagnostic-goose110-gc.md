# Client GC diagnostic

Diagnostic client/runtime evidence only; no performance, capacity, or rank claim.

Only completed phase logs were read. GC `@` is runtime-relative: the saved launch protocol bounds its phase-time offset to −5..0 seconds, but records no exact runtime-init clock anchor.

The first and last printed clock values are STW termination phases. The middle value is concurrent marking; a seconds-long middle value does not mean the application was stopped for seconds.

## 01-warmup-10000

Assessment: `INVALID_GENERATOR`; other classifications: INVALID_GENERATOR, INVALID_MONITOR, FAIL_SLO. This remains diagnostic evidence.

| Shard | Cycles | Largest individual STW, ms | Largest combined STW/cycle, ms | Longest concurrent mark, ms | Max live/goal heap, MiB | Max sampler lag, ms |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 36 | 13 | 13.014 | 1240 | 72/153 | 2084.62 |

Completed GC traces with an individual STW phase ≥1 second: **0**.

## 02-probe-100000

Assessment: `INCOMPLETE`; other classifications: . This remains diagnostic evidence.

| Shard | Cycles | Largest individual STW, ms | Largest combined STW/cycle, ms | Longest concurrent mark, ms | Max live/goal heap, MiB | Max sampler lag, ms |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 11 | 26 | 26.008 | 8243 | 119/207 | unavailable (missing result) |
| 1 | 11 | 27 | 27.011 | 4265 | 117/228 | 43474 |
| 2 | 11 | 91 | 91.006 | 2701 | 125/206 | unavailable (missing result) |
| 3 | 11 | 2.8 | 2.807 | 2351 | 120/227 | unavailable (missing result) |
| 4 | 11 | 67 | 67.006 | 11193 | 124/215 | unavailable (missing result) |

Completed GC traces with an individual STW phase ≥1 second: **0**.

Phase ended with: `TimeoutError: owned native generators exceeded phase deadline`. Missing native JSON results prevent complete timeline and end-to-end accounting; GC logs are partial evidence.

Shard 1 has a saved sampler gap from phase 57.090623 to 97.262906 seconds (40.172283 seconds elapsed). It lies wholly between completed GC cycles 10 and 11, whose conservative no-collection interval is phase 49.067910..112.574000 seconds after retaining the full 5-second runtime-origin uncertainty. Thus an overlapping recorded STW/concurrent collection does not explain that gap. This does not exclude background sweep/allocation work or host descheduling.

A completed concurrent-mark interval may overlap delayed sampling within the stated alignment range; that establishes timing compatibility, not causation. Neither GC nor server service time should be named as the cause without the corresponding trace and PostgreSQL evidence.
