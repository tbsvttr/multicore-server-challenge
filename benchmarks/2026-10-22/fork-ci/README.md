# Fork x86-64 validation

[Successful run](https://github.com/tbsvttr/multicore-server-challenge/actions/runs/39834209847), head `f57aad71a91d2cc8bb20ad651276a540f95008ee`, on the fork-only branch `validation/goose-native-2026-10-22`.

The submission Git tree is byte-identical to draft PR32 source `3e9087473da5c56d5800ae9ee00ac1e84c44a135`; only the narrowly triggered `.github/workflows/goose-validation.yml` was added. Fork Actions were already enabled. Exactly one workflow ran. The upstream draft/status/source branch was not changed.

Ubuntu24.04 x86_64, GCC13.3, PostgreSQL18.6: pinned Goose compiler built from source, original dev conformance197/197 with defaults, native checks228377, reliable pipe checks65589, Goose JWT FFI4000 assertions, original full-seed conformance197/197 with ARTICLE_BATCH1. Both deterministic seeds matched the reference fingerprints. The x86 app SHA256 is `7545aa192fc88721317ec7994f4e1567c96e785938de4d016d30c9da54b76679`.

This is clean source-build/correctness evidence, not a challenge hardware or performance result. Full logs, source equivalence, job/run metadata and the unchanged upstream draft receipt are retained here.

Runner hardware recorded4vCPUs,15989MiB RAM and3071MiB configured swap. BUILD_JOBS2 limited compilation parallelism; it does not describe the runner CPU count. No performance or8-core/no-swap compliance is inferred from this correctness job.
