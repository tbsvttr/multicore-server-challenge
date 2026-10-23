# Completed P2 diagnostic review

All three phases completed, but none qualified. No capacity score or first-place claim follows.

| Users | Recorded classification | p95 / p99, ms | Measured timeouts | PG samples / errors | Sampled blockers |
|---:|---|---:|---:|---:|---:|
| 10,000 | INVALID_CLOCK | 2670.591 / 9109.503 | 1,956 | 187 / 1 | 0 |
| 100,000 | INVALID_GENERATOR | 46989.311 / 49381.375 | 83,745 | 139 / 2 | 0 |
| 110,000 | INVALID_CLOCK | 20709.375 / 28671.999 | 90,730 | 146 / 1 | 0 |

All three fixed phases completed, but all remain invalid and fail their native SLO. No hold or capacity score exists.

Increasing client GOMAXPROCS to2 did not remove severe timer/active-user failures. The100k/110k client cgroup used about5.80/5.63CPU cores while the target used about3.27/4.02; this is consistent with client/VM scheduling pressure, not proof that the server is fault-free.

No blocker PID was sampled in any phase. The earlier P1 relation-lock episode was not reproduced, and cannot be the necessary explanation for this P2 collapse.

Sampled database work includes idle readers, active execution and WAL sync/write waits. Samples do not identify all queued or unsampled application work.

Completed GC traces show no seconds-long individual STW phase. A48.426-second sampler gap lies wholly between completed collections even with full anchor uncertainty; those recorded collections do not explain it. Allocation/sweeping, descheduling and queued application work are not thereby excluded.

Raw cpu.max changed from800000/100000 to1600000/200000 while retaining exactly8CPU. The frozen exact-string audit flags a budget mismatch; it does not demonstrate more than8CPU. Preserve the original verdicts because real scheduling, timing, active-user and SLO failures remain.

The charging guard remained safe and the host clock stayed consistent within1.27ms. Guest whole-phase clock drift111ms warm/146ms110 is real saved evidence but alone does not prove host sleep.

P1/P2 changes include both client concurrency and observer details, so this is not a pure causal comparison or a performance comparison. Initial collapse cause remains unresolved.

Review checks: 38/38. Source/binary: `23a14e8` / `7a7c31fb…`. The runtime was the submitted A revision; the B prototype was not used.

Cleanup receipts show the owned app group stopped, clone dropped and client exited without OOM. Target/PostgreSQL remained running and idle; the review did not change them.

The JSON retains all numeric waits, GC summaries, raw clock/resource settings and SHA-256 input receipts. This script reads saved files only.
