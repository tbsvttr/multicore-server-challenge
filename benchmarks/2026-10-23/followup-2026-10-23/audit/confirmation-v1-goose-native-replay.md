# Closed Goose B confirmation: native replay

PASS: 20 independent checks and 639 frozen phase checks. All 75 consumed saved files retained their hashes during the replay.

| Phase | Users | Ramp / measure / tail | Requests | p95 / p99 ms | Native / local | Errors / flags |
|---|---:|---|---:|---|---|---|
| warmup | 10,000 | 60 / 120 / 15 s | 318,061 | 6.667 / 7.371 | PASS / PASS | 0 / 0 |
| probe | 140,000 | 60 / 60 / 15 s | 2,229,366 | 11.623 / 188.159 | PASS / PASS | 0 / 0 |
| hold | 140,000 | 60 / 300 / 15 s | 11,109,776 | 10.903 / 239.615 | PASS / PASS | 0 / 0 |

The 140,000-user hold measured 37032.5867 requests/s over 300 seconds. All three phases have zero measured and full-timeline errors, complete synchronized measurement timelines, no native timer or whole-VM CPU flags, and no local CPU-scope exception. Every recorded assessment field matches the replay except its documented initial classification placeholder.

The frozen verifier independently decodes raw HDR histograms, reproduces exact merged counts/bins/quantiles/statuses/errors and native generator/SLO verdicts, and validates target/client budgets, clock/coverage, actual process witnesses, health and conformance receipts. Individual maximum CPU samples remain recorded; native CPU flagging uses the measurement average. The retained PG live-PID component CPU warning withholds that component estimate.

This is a saved-file B-only audit. Rust phases, active events/controller files and runtime state were not read. Whole-pair confirmation is pending. No exact capacity maximum, official rank, causal or promotion claim is made.

Detailed checks and consumed-file hashes: `confirmation-v1-goose-native-replay.json`.
