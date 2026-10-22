# Separate80k-user local comparison controller

Prepared only; no Docker execution. The active10k controller, helper files and frozen plans are unchanged. `multi-preparation-protected-hashes-before.json` / `multi-preparation-proof.json` prove that preparation preserved those files. The80k controller is independent code and creates its own `paired-multi-load/` evidence tree.

Prepare and review a plan:

```sh
python3 paired-multi-load.py --config paired-multi-load-example.json --plan rust-goose-80k-plan.json
```

Execution requires a separate explicit `--execute` call with that plan; stop the current10k comparison and any compilation/correctness traffic first. It refuses an occupied target port and never stops an unrelated app/container. The protocol is strictly80,000 total VUs, with no dynamic rescaling or replacement attempts: three pairs A/B, B/A, A/B, fresh original full-seed clone per case,60s ramp +60s measured +15s tail and65s connection drains. No official warmup, search or five-minute hold. This is a colocated ARM64 Mac diagnostic, not a score or proof of first place.

All four native generator processes share one separate2CPU/4GiB/no-swap load container. They have GOMAXPROCS1 each, the same start-at timestamp and pair run-id; box indices0–3 and disjoint offsets0/20k/40k/60k. Each20k-VU shard uses its own target address127.0.0.1/2/3/4:3000. Linux loopback/8 and the app's HOST0.0.0.0 listener support these addresses without interface aliases, sysctl changes or Docker networking changes. Per-destination ports avoid the single-target ephemeral tuple limit; the existing port range is read and checked per shard. Server plus PostgreSQL remain in the original shared8CPU/16GiB/no-swap container with no affinity.

The example compares pinned Rust PR7 against the current Goose binary. It records expected binary SHA256 and fails if rebuilt binaries differ. Rust's direct-binary case explicitly reproduces its8CPU defaults and start.sh settings, including READ_TAG_ROUTE1, READ_COMMENT_SET1 and READ_TAG_BATCH1; omitting those would disadvantage Rust. Goose defaults ARTICLE_BATCH0 until the earlier feature comparison selects a value. To change that value, edit the example and prepare a fresh plan before execution, retaining every older plan.

Every shard retains its raw JSON and console log, and is separately merged with the unmodified native tool for its own verdict. A second native merge combines all four histograms and counters exactly. The controller verifies4boxes/80kusers, synchronized metadata, disjoint indices/offsets, normal think scale and500k article count. The display target in native merged JSON is inherited from box0, while all four actual targets remain in raw metadata and command records.

Validity rules match the10k plan: retain native SLO/LG verdicts unchanged, mark native LG-limited invalid, require combined load-cgroup utilization<=75% of its2CPU quota and zero load OOM kills, and preserve the same1Hz sampling/gap check. A generator failure never counts as an app capacity failure. Four native processes read the same VM-wide `/proc/stat`; combined target/other workload CPU can therefore set native lg_limited even when the separate load quota has headroom. This limitation is retained and disclosed rather than bypassed.

Each case freezes app/source/tool hashes, archives source, records complete Docker configs and PG settings, launches one normal-user app process group, samples target/app/PG and combined generator cgroup resources, and cleans only owned process/database names. Native client and shared helpers are reused unchanged. All six attempts remain, including failures and invalid attempts. At80k the2CPU client budget may become limiting; do not silently increase it or rerun discarded trials. A new separately declared experiment is required for different resources.
