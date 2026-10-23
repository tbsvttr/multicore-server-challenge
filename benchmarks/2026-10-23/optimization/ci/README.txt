Prepared fork-only native x86 validation; NOT EXECUTED.

This package adds validation files only on a separate fork branch. It must not be copied onto the PR32 submission branch. The optimized PR source remains restricted to submissions/goose-native-tbsvttr/. Before building, validate.sh resolves the supplied source_ref to a full commit and asserts that the validation HEAD has the identical submission Git tree. It rejects any commit difference other than added files under the two allowed validation paths.

After Root selects and pushes the optimized PR source:
1. Create validation/goose-native-optimized-2026-10-23 directly from that exact source commit.
2. Copy goose-optimized-validation.yml to .github/workflows/goose-optimized-validation.yml.
3. Copy validate.sh and probes/* into .github/validation-goose/ (flatten probes/; the shell expects the Python and Go probe files beside itself).
4. Commit only these added validation paths. Check the submission tree against the PR source before pushing the separate validation branch.
5. The branch push starts only this workflow on tbsvttr/multicore-server-challenge. A manual dispatch may instead supply source_ref=<exact PR source SHA>. The PR head/draft state and source branch need no CI-file changes.

No branch, push, dispatch, Docker operation, compiler build, database query or application HTTP call was performed by the preparing agent. CLI reads were used only to pin public action/module metadata; local bash/YAML/Python syntax and source/hash checks do not execute the job.

The workflow uses Ubuntu24.04 native x86_64 and contents:read permission, with actions pinned to commits. Checkout/setup-go pins come from the previous successful fork validation; upload-artifact v4 was resolved by public read-only GitHub metadata. Go1.27.1 is fixed. PostgreSQL18 uses the exact image digest from the prior successful x86 job (which reported18.6). The runner's actual CPU/memory/swap/identity is recorded. This is correctness/build evidence, not official challenge hardware, no-swap compliance, a capacity score or a performance claim.

validate.sh accepts --submission submissions/<folder>, --source-ref <branch-or-commit>, and --out <evidence-directory>. The normal runner user executes the compiler/app build and all servers; sudo is used only for the original dependency installer. A clean compiler checkout is required, GOOSE_BIN is cleared for the first build, and the full f605 compiler commit plus source-archive SHA256 are verified. Later builds and the stock3e908747 baseline reuse that same verified compiler/runtime.

Checks and retained evidence:
- Original dev/full seed scripts verify all seven table counts and content fingerprints; their logs and unchanged original harness hashes are retained.
- The original197-step suite runs on dev defaults, full defaults, full with READ_BATCH_US=5000/ARTICLE_BATCH=1 and one worker, and the selected W2/PG_READERS3/HASHERS2/ARTICLE1/READ5000us/WRITE1000us configuration.
- Native293966 assertions,4000 Goose JWT FFI assertions,252 bcrypt lane comparisons at costs4/5/10; exact pass counts are asserted.
- Original stock3e908747 is built from git archive with the same pinned compiler. Two read-only servers use one private full-seed clone; candidate WORKERS1/READ_BATCH_US5000 executes the1664-request read oracle, including12 actual batch-SQL witnesses, viewer isolation, empty/missing rows, ordering, capped counts and committed mutations.
- Quiet500000us read wake/deadline reset and writer independence; READ_BATCH_US0 checks disabled-mode liveness and response correctness, not a strict immediate-dispatch latency bound.
- A separate private clone runs the deferred-COMMIT/no-early-HTTP and grouped-rollback probe, followed by the concurrent-favorite fresh-response probe. Temporary triggers/functions used by the commit probe exist only in that disposable correctness DB and are removed; no schema modification is used by performance measurements.
- The article-update and favorite/rename race probe must pass its fixed/fresh expectation on the selected configuration; baseline stale-reproduction mode is never used.
- The embedded-NUL password probe checks cost10 interoperability against trusted Go/x-crypto0.58.0 in both directions, wrong-prefix rejection, and unchanged PostgreSQL text/72-byte guards. The helper runs from repo/bench using a temporary pinned modfile/sum in the evidence directory; original bench/go.mod and go.sum are untouched.
- All test fixtures, owned process groups and private DBs are removed. Process-group shutdown waits at most3s after TERM and2s after KILL, then records failure instead of hanging; DB cleanup commands have20s bounds. Logs, process UID/limits, source-tree receipt, binary hashes and final artifact hash manifest are uploaded even when a test fails.

The harness is parameterized because the final capacity winner/source head is not yet selected. Its checks intentionally fail if that source does not contain the new optional read-window/bcrypt/read-batch paths. The package does not change a candidate default or interpret a local calibration result.

All correctness clone names now begin mc_pair_ci_, as required by the race/NUL safety probes. The selected configuration is recorded for correctness coverage only; fixed80k calibration CPU differences do not establish capacity or rank.
