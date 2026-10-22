# Leaderboard

Every submission on the same box: **8 dedicated vCPU / 16 GB**, Postgres 18 on the same box, full seed, the load generator on a separate machine. Score = the most users held for a 5-minute run with p95 < 500 ms, p99 < 1 s and < 1% errors ([how it's scored](README.md#scoring)). The video's four examples were re-run on this same box so everything compares like with like.

| # | Users | Submission | PR | Front | req/s | p95 ms | p99 ms | CPU: app / Postgres | Note |
|--:|--:|---|---|---|--:|--:|--:|---|---|
| 1 | **100,000** | [rust-tokio-Scooter1337](submissions/rust-tokio-Scooter1337) | [#7](https://github.com/arjaythedev/multicore-server-challenge/pull/7) @Scooter1337 | direct | 26,279 | 119 | 185 | 20% / 70% |  |
| 2 | **95,000** | [csharp-sockets-jh-d](submissions/csharp-sockets-jh-d) | [#22](https://github.com/arjaythedev/multicore-server-challenge/pull/22) @jh-d | direct | 24,696 | 493 | 737 | 21% / 75% |  |
| 3 | **84,000** | [c-iouring-tigokraft](submissions/c-iouring-tigokraft) | [#10](https://github.com/arjaythedev/multicore-server-challenge/pull/10) @tigokraft | direct | 21,262 | 339 | 421 | 18% / 80% |  |
| 4 | **84,000** | [cobol-gnucobol-benmandrew](submissions/cobol-gnucobol-benmandrew) | [#15](https://github.com/arjaythedev/multicore-server-challenge/pull/15) @benmandrew | direct | 21,292 | 361 | 461 | 20% / 75% |  |
| 5 | **84,000** | [csharp-kestrel-xeonfx](https://github.com/arjaythedev/multicore-server-challenge/pull/8) | [#8](https://github.com/arjaythedev/multicore-server-challenge/pull/8) @XeonFX | direct | 20,906 | 404 | 467 | 25% / 74% | Not merged yet: bcrypt comes from a prebuilt NuGet package; waiting for the source in the folder |
| 6 | **80,000** | [rust-mio-foovoo](https://github.com/arjaythedev/multicore-server-challenge/pull/11) | [#11](https://github.com/arjaythedev/multicore-server-challenge/pull/11) @FooVoo | direct | 20,710 | 474 | 752 | 18% / 75% | Not merged yet: build.sh needs rustc on PATH (`export PATH=/usr/local/cargo/bin:$PATH`); scored with that one line added |
| 7 | **68,000** | [cpp-asio-c-hatton](submissions/cpp-asio-c-hatton) | [#4](https://github.com/arjaythedev/multicore-server-challenge/pull/4) @C-Hatton | direct | 17,887 | 94 | 174 | 27% / 71% |  |
| 8 | **58,000** | [rust-hyper-cknutson12](submissions/rust-hyper-cknutson12) | [#1](https://github.com/arjaythedev/multicore-server-challenge/pull/1) @cknutson12 | direct | 15,075 | 223 | 367 | 29% / 69% |  |
| 9 | **46,000** | [python-uvloop-bensgilbert](https://github.com/arjaythedev/multicore-server-challenge/pull/13) | [#13](https://github.com/arjaythedev/multicore-server-challenge/pull/13) @bensgilbert | direct | 11,572 | 423 | 519 | 38% / 58% | Not merged yet: restarts crashed workers (rule 9). No worker restarted during the run, so the score stands |
| 10 | **33,000** | [lua-openresty-yar0slav](submissions/lua-openresty-yar0slav) | [#19](https://github.com/arjaythedev/multicore-server-challenge/pull/19) @yar0slav | direct | 8,616 | 432 | 783 | 37% / 49% |  |
| 11 | **32,000** | [elixir-raw-foovoo](submissions/elixir-raw-foovoo) | [#12](https://github.com/arjaythedev/multicore-server-challenge/pull/12) @FooVoo | direct | 7,999 | 323 | 382 | 37% / 48% |  |
| 12 | **25,000** | [pony-stallion-contact-red](https://github.com/arjaythedev/multicore-server-challenge/pull/24) | [#24](https://github.com/arjaythedev/multicore-server-challenge/pull/24) @redvers | direct | 6,496 | 497 | 986 | 32% / 54% | Scored at an earlier commit (a38283c); the author pushed 5 more commits (batched bcrypt, SQL changes) during the batch, re-run queued |
| 13 | **23,000** | [d-arsd-cyrusmsk](submissions/d-arsd-cyrusmsk) | [#16](https://github.com/arjaythedev/multicore-server-challenge/pull/16) @cyrusmsk | direct | 5,952 | 373 | 577 | 24% / 66% |  |
| 14 | **20,000** | [swift-hummingbird-denizakya](submissions/swift-hummingbird-denizakya) | [#9](https://github.com/arjaythedev/multicore-server-challenge/pull/9) @denizak | nginx | 5,077 | 339 | 400 | 48% / 40% (+ Nginx 10%) |  |
| 15 | **20,000** | [v-fasthttp-ulises-jeremias](https://github.com/arjaythedev/multicore-server-challenge/pull/2) | [#2](https://github.com/arjaythedev/multicore-server-challenge/pull/2) @ulises-jeremias | direct | 5,193 | 351 | 563 | 12% / 63% | Not merged yet: install.sh fails on a clean box (V's bootstrap `vc` isn't pinned); scored with vc pinned by hand |
| 16 | **8,300** | [csharp-efcore-xeonfx](submissions/csharp-efcore-xeonfx) | [#20](https://github.com/arjaythedev/multicore-server-challenge/pull/20) @XeonFX | direct | 2,108 | 447 | 720 | 19% / 78% |  |
| 17 | **1,100** | [perl-mojolicious-denizakya](submissions/perl-mojolicious-denizakya) | [#23](https://github.com/arjaythedev/multicore-server-challenge/pull/23) @denizak | nginx | 287 | 197 | 327 | 8% / 3% (+ Nginx 0%) |  |

## Not scored

| Submission | PR | Why |
|---|---|---|
| [c-iouring-27bhd](https://github.com/arjaythedev/multicore-server-challenge/pull/5) | [#5](https://github.com/arjaythedev/multicore-server-challenge/pull/5) @27bhd | No 5-minute hold passed: POST /api/articles takes ~2 s even on an idle box and blocks its worker, so p99 > 1 s from ~100 users (2-minute probes passed at 100) |
| [d-vibe-cyrusmsk](https://github.com/arjaythedev/multicore-server-challenge/pull/18) | [#18](https://github.com/arjaythedev/multicore-server-challenge/pull/18) @cyrusmsk | Crashed 11 minutes into the run (SIGILL, core dumped) at 8,000 users; PR #18 also needs pinned dependencies |

CPU is the share of the whole box (8 cores) used by your server and by Postgres during the scored 5 minutes. Raw results for every run (each probe and hold, per-endpoint latencies, the box's CPU every second) are kept and can be shared on request.
