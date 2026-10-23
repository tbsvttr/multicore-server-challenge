# Actual feed-window SQL diagnostic audit

All31 actual generated-SQL cases return identical ordered values. The372 measured EXPLAIN plans follow alternating AB/BA order after warmups. No measured plan reads disk or spills temporary data. This is a query diagnostic, not a native workload/capacity result.

| Viewer pattern | Offset | GM candidate/baseline median time | Interpretation |
|---|---:|---:|---|
| distinct | 0 | 0.949654 | 5.03% lower time |
| distinct | 40 | 1.118788 | -11.88% lower time |
| distinct | 600 | 1.023304 | -2.33% lower time |
| duplicate | 0 | 0.151766 | 84.82% lower time |
| duplicate | 40 | 0.188317 | 81.17% lower time |
| duplicate | 600 | 0.140449 | 85.96% lower time |

The distinct-viewer page1 group improves about5.0% overall, but its2-request batch regresses5.8%. Offset40 regresses at every measured size (6.5–19.3%, GM11.9%); offset600 has GM2.3% overhead. The mixed sparse/zero/deep case regresses2.8%. Duplicate cases gain81–86% in the equal-weight group summaries, mostly from deduplicating requests/counts/pages. Those gains must not be blended into a realistic unique-user headline.

| Case | Baseline ms | Window ms | Time change | Fast / fallback child loops | Recent rows | Unique enriched IDs |
|---|---:|---:|---:|---:|---:|---:|
| feed-2-distinct-offset0 | 1.2025 | 1.2720 | +5.78% | 1 / 1 | 128.0 | 20 |
| feed-2-distinct-offset40 | 1.5400 | 1.8370 | +19.29% | 0 / 2 | 200.0 | 20 |
| feed-2-distinct-offset600 | 3.8310 | 4.0740 | +6.34% | 0 / 2 | 0 | 20 |
| feed-2-duplicate-offset0 | 1.3835 | 0.6385 | -53.85% | 1 / 0 | 46.0 | 10 |
| feed-2-duplicate-offset40 | 1.9640 | 1.2355 | -37.09% | 0 / 1 | 200.0 | 10 |
| feed-2-duplicate-offset600 | 5.8375 | 3.0300 | -48.09% | 0 / 1 | 0 | 10 |
| feed-4-distinct-offset0 | 2.1795 | 2.0685 | -5.09% | 1 / 3 | 128.0 | 36 |
| feed-4-distinct-offset40 | 2.5820 | 2.9000 | +12.32% | 0 / 4 | 200.0 | 40 |
| feed-4-distinct-offset600 | 5.7795 | 5.8785 | +1.71% | 0 / 4 | 0 | 40 |
| feed-4-duplicate-offset0 | 2.6870 | 0.6525 | -75.72% | 1 / 0 | 46.0 | 10 |
| feed-4-duplicate-offset40 | 3.8540 | 1.2685 | -67.09% | 0 / 1 | 200.0 | 10 |
| feed-4-duplicate-offset600 | 11.4870 | 3.0695 | -73.28% | 0 / 1 | 0 | 10 |
| feed-8-distinct-offset0 | 4.4055 | 3.9780 | -9.70% | 2 / 6 | 128.0 | 65 |
| feed-8-distinct-offset40 | 5.7195 | 6.2445 | +9.18% | 0 / 8 | 200.0 | 75 |
| feed-8-distinct-offset600 | 13.2670 | 13.4325 | +1.25% | 0 / 8 | 0 | 80 |
| feed-8-duplicate-offset0 | 5.2785 | 0.7325 | -86.12% | 1 / 0 | 46.0 | 10 |
| feed-8-duplicate-offset40 | 7.6405 | 1.3330 | -82.55% | 0 / 1 | 200.0 | 10 |
| feed-8-duplicate-offset600 | 23.0025 | 3.1350 | -86.37% | 0 / 1 | 0 | 10 |
| feed-16-distinct-offset0 | 7.9245 | 7.5005 | -5.35% | 2 / 14 | 128.0 | 117 |
| feed-16-distinct-offset40 | 9.7665 | 10.3985 | +6.47% | 0 / 16 | 200.0 | 145 |
| feed-16-distinct-offset600 | 20.8450 | 21.1300 | +1.37% | 0 / 16 | 0 | 150 |
| feed-16-duplicate-offset0 | 10.6850 | 0.9660 | -90.96% | 1 / 0 | 46.0 | 10 |
| feed-16-duplicate-offset40 | 16.2620 | 1.7875 | -89.01% | 0 / 1 | 200.0 | 10 |
| feed-16-duplicate-offset600 | 45.9745 | 3.3515 | -92.71% | 0 / 1 | 0 | 10 |
| feed-32-distinct-offset0 | 16.4330 | 14.7930 | -9.98% | 6 / 26 | 128.0 | 183 |
| feed-32-distinct-offset40 | 20.9355 | 23.5625 | +12.55% | 0 / 32 | 200.0 | 264 |
| feed-32-distinct-offset600 | 48.4805 | 49.0030 | +1.08% | 0 / 32 | 0 | 277 |
| feed-32-duplicate-offset0 | 20.7635 | 1.1890 | -94.27% | 1 / 0 | 46.0 | 10 |
| feed-32-duplicate-offset40 | 30.3370 | 1.8095 | -94.04% | 0 / 1 | 200.0 | 10 |
| feed-32-duplicate-offset600 | 91.7965 | 3.6405 | -96.03% | 0 / 1 | 0 | 10 |
| feed-mixed-sparse-and-limits | 2.2460 | 2.3080 | +2.76% | 0 / 4 | 0 | 0 |

Actual branch witnesses:

- N8/distinct/offset0 executes the fast child2 times and indexed fallback6 times. At offset40 it executes fast0/fallback8: the extra window does not fill the requested prefix.
- N8/duplicate/offset0 executes one deduplicated fast page and no fallback child. This confirms the one-time filter prevents the indexed branch from running when the prefix is complete.
- Deep offset600 and the mixed sparse/zero/deep case skip the recent CTE entirely (Actual Loops0), then retain the indexed fallback and synthetic empty-page rows.
- Every candidate enrichment CTE returns exactly the number of distinct non-null article IDs in that case’s output.

Selection implication: measure sharing-only separately before deciding whether the recent-window complexity helps. Current evidence favors testing READ_BATCH_US independently, and either sharing-only or a first-page-only window variant as the next whole-workload comparison. The full original window is not a consistent query win for distinct viewers.

Limitations: No native workload or capacity was measured by this audit. Duplicate-viewer gains are not representative of mostly distinct active VUs. Only offsets0/40/600 plus one mixed case are measured; offsets10/20/30 are absent. No candidate recent window exceeded200 rows in these actual plans;512 boundary has model/static coverage only. The comparison changes simple lateral batching into sharing+window; it does not isolate window versus sharing-only. EXPLAIN row/timing fields are instrumented and rounded; node times are inclusive and must not be added as CPU cost. Each timing point is a warmed single-query batch under one local environment, not a maximum throughput result.
