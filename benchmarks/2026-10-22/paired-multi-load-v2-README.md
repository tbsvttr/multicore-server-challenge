# Corrected local80k comparison launcher

`paired-multi-load-v2.py` uses only the new `lab-target-control-v2.py`. Each attempt freezes and hashes the controller, helper and unchanged monitor before using their frozen copies. Previous controllers, helpers, plans and results remain unchanged.

Every case launches identically through `runuser -u challenge -- prlimit --nofile=200000:200000 -- <frozen binary>`. Docker's configured limit alone was insufficient: a separate reproduction showed plain runuser lowers its child soft limit. The new helper records the actual executable PID, process group, start ticks, all four UID values and raw `/proc/<pid>/limits`/status after health. A same-UID inspector reads those files without adding Docker capabilities. Startup, pre-load and post-load checks require the expected normal UID and actual soft/hard limits of at least200000; missing or inadequate evidence cannot qualify.

The protocol is unchanged:80,000 VUs across four20k shards to127.0.0.1–4, one shared2CPU/4GiB load container, GOMAXPROCS1 per shard, synchronized start and disjoint user offsets. Three alternating pairs use fresh full-seed clones,60s ramp +60s measured +15s tail, with65s drains. Server and PostgreSQL share8CPU/16GiB/no-swap without affinity. Plans `rust-goose-80k-v2-plan.json` and `pr31-goose-80k-v2-plan.json` retain the original case settings and pinned binaries. No app source or native generator changed.

The earlier aborted80k run remains retained: its Rust arm's original native FAIL_SLO/EMFILE data are preserved and independently classified INVALID_TARGET_NOFILE; its actual historical numeric child limit was never captured. The separate runuser reproduction is not presented as that old process's measurement. The first health-only v2 attempt also remains retained: its missing executable witness was rejected and cleaned before any load. The corrected same-UID verification passed all three apps on all four addresses, with actual UID501 and limits200000/200000; every app/database was stopped/dropped.25 regression fixtures and60 independent raw-witness checks passed.

Native SLO and generator verdicts remain untouched. Native LG-limited, insufficient combined generator headroom, load OOM, missing monitor coverage or invalid process limits cannot qualify. Post-tail health and target OOM checks remain enforced. Every attempted arm stays in its own record; no failed or invalid trial is replaced in a result average.

These are colocated ARM64 Mac/Docker diagnostic probes, without the official warmup/search/five-minute holds or external load machines. VM-wide CPU sampling can flag native LG-limited even when the separate generator quota has headroom. Fixed80k results cannot establish the official x86 leaderboard position. No full v2 load was run during preparation.

Receipts: `nofile-v2/preparation-proof.json`, `nofile-v2/launch-verification-2/`, `nofile-v2/launcher-v2.patch` and `audit/nofile-v2-actual-witness-audit.json`.
