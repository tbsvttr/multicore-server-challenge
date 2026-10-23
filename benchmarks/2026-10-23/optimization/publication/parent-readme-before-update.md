# Official multicore comparison — 23 October 2026

Snapshot: 2026-10-23T06:59:05.240087+00:00. The [maintainer’s official leaderboard](https://github.com/arjaythedev/multicore-server-challenge/blob/c3012257f2ee3dd2ccc72ada2eeba2b0d1278e8e/LEADERBOARD.md) already compares all 29 scored implementations/examples on the same challenge box. This record adds the two active submissions without a score, giving one row for each of the 31 current implementations/examples. It does not rerun them on the Mac.

Our Goose is **#8 at 65,000 users**, compared with Rust #7 at **100,000 users**. Goose holds 35,000 fewer users (35.00% below the leader); matching 100,000 would require 53.85% more users than its current score. Goose #31 holds 62,000 users. Our PR remains a draft at source `3e908747`; the tested proposal to change local defaults was not applied.

The official conditions are 8 dedicated vCPUs and 16 GB, with the application, PostgreSQL 18 and any Nginx sharing the target budget, full seed, and load generation on another machine. Score is the highest user count sustained for a five-minute run with p95 <500 ms, p99 <1 s and <1% errors.

**Latency and request rate are measured at each row’s own scored load. They are not matched-load latency or throughput comparisons.** Unscored means unknown, not zero.

| Official rank | Implementation | Status | Users | Req/s | p95 / p99 ms | Front | CPU app / PG | Caveat |
|---:|---|---|---:|---:|---:|---|---|---|
| 1 | [#7 rust-tokio-Scooter1337](https://github.com/arjaythedev/multicore-server-challenge/pull/7) | Scored; merged | 100,000 | 26,279 | 119 / 185 | direct | 20% / 70% | — |
| 2 | [#22 csharp-sockets-jh-d](https://github.com/arjaythedev/multicore-server-challenge/pull/22) | Scored; merged | 95,000 | 24,696 | 493 / 737 | direct | 21% / 75% | — |
| 3 | [#10 c-iouring-tigokraft](https://github.com/arjaythedev/multicore-server-challenge/pull/10) | Scored; merged | 84,000 | 21,262 | 339 / 421 | direct | 18% / 80% | — |
| 4 | [#15 cobol-gnucobol-benmandrew](https://github.com/arjaythedev/multicore-server-challenge/pull/15) | Scored; merged | 84,000 | 21,292 | 361 / 461 | direct | 20% / 75% | — |
| 5 | [#8 csharp-kestrel-xeonfx](https://github.com/arjaythedev/multicore-server-challenge/pull/8) | Scored; open | 84,000 | 20,906 | 404 / 467 | direct | 25% / 74% | Not merged yet: bcrypt comes from a prebuilt NuGet package; waiting for the source in the folder |
| 6 | [#11 rust-mio-foovoo](https://github.com/arjaythedev/multicore-server-challenge/pull/11) | Scored; merged | 80,000 | 20,710 | 474 / 752 | direct | 18% / 75% | — |
| 7 | [#4 cpp-asio-c-hatton](https://github.com/arjaythedev/multicore-server-challenge/pull/4) | Scored; merged | 68,000 | 17,887 | 94 / 174 | direct | 27% / 71% | — |
| 8 | [#32 goose-native-tbsvttr](https://github.com/arjaythedev/multicore-server-challenge/pull/32) **(ours)** | Scored; open draft | 65,000 | 17,125 | 27 / 721 | direct | 18% / 71% | Not merged yet: the pull request is marked as a draft |
| 9 | [#31 goose-epoll-xeonfx](https://github.com/arjaythedev/multicore-server-challenge/pull/31) | Scored; merged | 62,000 | 16,311 | 30 / 842 | direct | 17% / 71% | — |
| 10 | [#28 go-epoll-o7livetype](https://github.com/arjaythedev/multicore-server-challenge/pull/28) | Scored; merged | 61,000 | 15,865 | 351 / 484 | direct | 20% / 73% | — |
| 11 | [#1 rust-hyper-cknutson12](https://github.com/arjaythedev/multicore-server-challenge/pull/1) | Scored; merged | 58,000 | 15,075 | 223 / 367 | direct | 29% / 69% | — |
| 12 | [#30 kotlin-vertx-canleon](https://github.com/arjaythedev/multicore-server-challenge/pull/30) | Scored; merged | 46,000 | 11,923 | 352 / 440 | direct | 37% / 51% | — |
| 13 | [#13 python-uvloop-bensgilbert](https://github.com/arjaythedev/multicore-server-challenge/pull/13) | Scored; open | 46,000 | 11,572 | 423 / 519 | direct | 38% / 58% | Not merged yet: restarts crashed workers (rule 9). No worker restarted during the run, so the score stands |
| 14 | [#27 go-fasthttp-o7livetype](https://github.com/arjaythedev/multicore-server-challenge/pull/27) | Scored; merged | 44,000 | 11,321 | 496 / 620 | nginx | 23% / 53% (+ Nginx 19%) | — |
| 15 | [#29 kotlin-ktor-canleon](https://github.com/arjaythedev/multicore-server-challenge/pull/29) | Scored; merged | 44,000 | 10,948 | 496 / 664 | direct | 45% / 49% | — |
| 16 | [#19 lua-openresty-yar0slav](https://github.com/arjaythedev/multicore-server-challenge/pull/19) | Scored; merged | 33,000 | 8,616 | 432 / 783 | direct | 37% / 49% | — |
| 17 | [#12 elixir-raw-foovoo](https://github.com/arjaythedev/multicore-server-challenge/pull/12) | Scored; merged | 32,000 | 7,999 | 323 / 382 | direct | 37% / 48% | — |
| 18 | [#25 rust-urus-markk116](https://github.com/arjaythedev/multicore-server-challenge/pull/25) | Scored; merged | 32,000 | 8,313 | 438 / 540 | direct | 27% / 46% | — |
| 19 | [#24 pony-stallion-contact-red](https://github.com/arjaythedev/multicore-server-challenge/pull/24) | Scored; merged | 25,000 | 6,454 | 473 / 733 | direct | 33% / 52% | — |
| 20 | [go example](https://github.com/arjaythedev/multicore-server-challenge/tree/c3012257f2ee3dd2ccc72ada2eeba2b0d1278e8e/examples/go) | Scored; reference | 24,000 | 6,192 | 483 / 701 | nginx | 27% / 47% (+ Nginx 11%) | — |
| 21 | [#16 d-arsd-cyrusmsk](https://github.com/arjaythedev/multicore-server-challenge/pull/16) | Scored; merged | 23,000 | 5,952 | 373 / 577 | direct | 24% / 66% | — |
| 22 | [rust example](https://github.com/arjaythedev/multicore-server-challenge/tree/c3012257f2ee3dd2ccc72ada2eeba2b0d1278e8e/examples/rust) | Scored; reference | 22,000 | 5,734 | 233 / 334 | nginx | 25% / 50% (+ Nginx 11%) | — |
| 23 | [java example](https://github.com/arjaythedev/multicore-server-challenge/tree/c3012257f2ee3dd2ccc72ada2eeba2b0d1278e8e/examples/java) | Scored; reference | 21,000 | 5,528 | 104 / 182 | nginx | 30% / 46% (+ Nginx 11%) | — |
| 24 | [#9 swift-hummingbird-denizakya](https://github.com/arjaythedev/multicore-server-challenge/pull/9) | Scored; merged | 20,000 | 5,077 | 339 / 400 | nginx | 48% / 40% (+ Nginx 10%) | — |
| 25 | [#2 v-fasthttp-ulises-jeremias](https://github.com/arjaythedev/multicore-server-challenge/pull/2) | Scored; open | 20,000 | 5,193 | 351 / 563 | direct | 12% / 63% | Not merged yet: install.sh fails on a clean box (V's bootstrap `vc` isn't pinned); scored with vc pinned by hand |
| 26 | [#26 bun-native-PetarGeorgiev-hash](https://github.com/arjaythedev/multicore-server-challenge/pull/26) | Scored; merged | 18,000 | 4,591 | 296 / 736 | direct | 18% / 33% | — |
| 27 | [python example](https://github.com/arjaythedev/multicore-server-challenge/tree/c3012257f2ee3dd2ccc72ada2eeba2b0d1278e8e/examples/python) | Scored; reference | 10,000 | 2,634 | 82 / 150 | nginx | 49% / 25% (+ Nginx 6%) | — |
| 28 | [#20 csharp-efcore-xeonfx](https://github.com/arjaythedev/multicore-server-challenge/pull/20) | Scored; merged | 8,300 | 2,108 | 447 / 720 | direct | 19% / 78% | — |
| 29 | [#23 perl-mojolicious-denizakya](https://github.com/arjaythedev/multicore-server-challenge/pull/23) | Scored; merged | 1,100 | 287 | 197 / 327 | nginx | 8% / 3% (+ Nginx 0%) | — |
| — | [#5 c-iouring-27bhd](https://github.com/arjaythedev/multicore-server-challenge/pull/5) | Unscored; open | — | — | — | — | — | No 5-minute hold passed: POST /api/articles takes ~2 s even on an idle box and blocks its worker, so p99 > 1 s from ~100 users (2-minute probes passed at 100) |
| — | [#17 d-vibe-cyrusmsk](https://github.com/arjaythedev/multicore-server-challenge/pull/17) | Unscored; open | — | — | — | — | — | Vibe.D standard variant; no published official score. Distinct from closed light variant #18. |

Closed historical variants are excluded from the current table. [D Vibe.D light #18](https://github.com/arjaythedev/multicore-server-challenge/pull/18) is a separate variant from open standard #17; the maintainer reports SIGILL 11 minutes into an 8,000-user run and unpinned dependencies, so it has no official passing score. Closed predecessors [#14](https://github.com/arjaythedev/multicore-server-challenge/pull/14) and [#21](https://github.com/arjaythedev/multicore-server-challenge/pull/21) are retained in the JSON history and source inventory.

Sources are pinned at upstream commit [`c3012257`](https://github.com/arjaythedev/multicore-server-challenge/tree/c3012257f2ee3dd2ccc72ada2eeba2b0d1278e8e), actual Git tree `dbabfe14215dbfd78f449d25f6a42cd9639e4719`, and leaderboard blob `1e48908381e0a0b70f09d306da184ed2e5130a8a`. [Machine-readable comparison](official-comparison.json) and [source inventory](inventory/inventory.json) retain PR heads, canonical source folders/trees, script hashes, state and caveats. Current source pins do not prove the exact revision used for a historical score. Merged Rust #11 and #25 have upstream build-script changes relative to their PR heads; those paths are explicitly recorded.

The maintainer says raw probe/hold and per-endpoint/CPU records are available on request; those trial files are not public in this snapshot. No new request was sent. Previous local experiments remain historical evidence and do not replace the official batch above.
