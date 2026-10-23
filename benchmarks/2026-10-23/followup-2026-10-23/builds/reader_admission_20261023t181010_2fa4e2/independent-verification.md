# Independent reader-admission verification

PASS: all 26 recorded probe checks and 28 independent file checks.

This verifies saved isolated correctness evidence only. It establishes no native capacity, performance gain, or rank. No Docker, SQL, network, probe execution, or process inspection/control was performed.

- All 36 frozen source hashes equal before/after snapshots and the selected candidate; source manifest recomputes exactly.
- Frozen and selected binary SHA-256: `9016ff93e924c0d94652490ac895d1fbc64153fd9d3ea4b8b52b66ae892c3424`.
- Saved actual app/proxy observations show UID 501 throughout and NOFILE soft/hard 200000. Owned stop/drop and fixture-cleanup receipts match.
- The complete stopped-observer log has 1848 records, 533 reader Syncs, matching Readies, cap 1, and maximum four Execute messages per reader Sync.
- All 24 abandoned-slug hashes are absent from scalar and binary-array Bind values; original favorite s19 and UPDATE s17 bind exactly once each.
- Original probe wire-prefix receipt recomputes byte-for-byte; final wire SHA-256 is `52d00814cd3de6274bc6d381933aae23192d1c9ea693d7ea5e82fe86441c2df3`.
- JSON receipt includes hashes for all 89 original checkpoint files, including the original frozen executable.

Runtime and cleanup conclusions use saved snapshots/receipts, not a new live check. Cancellation evidence shows no matching Bind in the observed complete log, not proof of application parsing for every canceled HTTP request.
