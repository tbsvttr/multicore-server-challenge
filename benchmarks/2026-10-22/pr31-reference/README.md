# PR #31 portable, correctness-corrected local reference

This is a comparator derived from XeonFX's Goose submission, not the original submitted source or an official result. The unchanged 17-file source snapshot is in `original-source/`; the disclosed portable derivative is in `source/`.

Original source: [XeonFX/multicore-server-challenge, commit 43e0919ae5b693c1d3c1e8828b74bb774ef92ee0](https://github.com/XeonFX/multicore-server-challenge/tree/43e0919ae5b693c1d3c1e8828b74bb774ef92ee0/submissions/goose-epoll-xeonfx), submitted as [PR #31](https://github.com/arjaythedev/multicore-server-challenge/pull/31). Its original read batching credits Scooter1337's Rust PR #7. The original MIT copyright and permission terms are preserved in `LICENSE` and `source/LICENSE`.

This reference keeps the original Goose JSON escaping, HMAC/SHA/JWT implementation, key initialization, bcrypt computation, scheduler and PostgreSQL driver. It includes neither our native JSON/HMAC primitives nor article batching. The only runtime changes are:

- Explicit C slice/syscall adapters and correct native epoll layout on ARM; the x86 epoll path remains zero-copy. Standalone runtime headers also make the original aggregate-style `read`/`write` extern declarations collide with libc declarations, which the adapter names avoid.
- The same reliable delivery of completed 72-byte bcrypt replies used by the candidate: full nonblocking pipes and interrupted calls wait/retry rather than discard completed jobs.
- The same PostgreSQL connection guard, leaving the original defaults unchanged at four loops, three readers plus one writer per loop.
- The same favorite correctness repair: the mutation commits before a separate article read constructs the response. An inherited concurrent-write probe reproduced a stale favorite count without this repair. Retried reads cannot replay a committed mutation.

The build uses the same pinned Goose source commit and archive SHA256, `-O2` standalone generation, and GCC `-O3 -march=native -flto=2 -fno-semantic-interposition -fno-plt` settings as the candidate. It links only the syscall/pipe helper and system math/thread libraries. Ubuntu package installation/bootstrap scripts and ignored output paths are adjusted to support that build. No OpenSSL or native JSON implementation is linked.

`manifest.json` records every original/reference file hash and why each file changed. `changes.patch` is the exact patch against `original-source/`. `original-source-sha256.txt` and `reference-source-sha256.txt` are separate fingerprints. The source README marks its inherited GCP measurements as historical upstream claims, not measurements of this derivative.

Build/validation status: **built successfully; unchanged dev and full conformance suites each pass 197/197**. Both logs identify the same binary, SHA-256 `5679b2f84562b352aa80faa6491ee9a6496224333881d2d96e585d468a6b67e2`. All 20 source files still match the prepared manifest. See `build-validation.json`, `conformance-dev.log` and `conformance-full.log`. The original `PREPARED_UNBUILT` manifest/preparation status is a historical snapshot; the receipt records the later successful builds. No comparative load measurement or official score is claimed. A later same-host comparison must use the same fresh full-seed copy, PostgreSQL configuration, combined resource budget, process settings, load generator, order balancing and measurement protocol for both implementations. Results from this ARM64 local reference cannot establish PR #31's official x86 score or a first-place challenge ranking.

To reproduce the build after any active run has stopped, use the same normal user and pinned compiler:

```sh
cd source
GOOSE_BIN=/opt/goose/build/goose bash build.sh
```

Omitting `GOOSE_BIN` builds the pinned compiler from source inside this reference. `start.sh` remains byte-identical to the original. Do not replace a running benchmark process with this reference until the controller has finished its current run.
