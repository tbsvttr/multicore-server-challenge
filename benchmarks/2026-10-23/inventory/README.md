# Pinned implementation inventory

Snapshot 2026-10-23T06:59:05.240087+00:00; upstream `c3012257f2ee3dd2ccc72ada2eeba2b0d1278e8e`, actual Git tree `dbabfe14215dbfd78f449d25f6a42cd9639e4719`.

30 PR records: 21 merged, 6 open, 3 closed historical. Current coverage is 27 submission PRs including ours, plus 4 reference examples. Official scored rows 29; active unscored PRs #5 and #17. No build or benchmark was run.

| Language/build group | Current entries |
|---|---|
| C | pr-5, pr-10 |
| C# | pr-8, pr-20, pr-22 |
| C++ | pr-4 |
| COBOL | pr-15 |
| D | pr-16, pr-17 |
| Elixir | pr-12 |
| Go | pr-27, pr-28, examples-go |
| Goose | pr-31, pr-32 |
| Java | examples-java |
| Kotlin | pr-29, pr-30 |
| Lua | pr-19 |
| Perl | pr-23 |
| Pony | pr-24 |
| Python | pr-13, examples-python |
| Rust | pr-1, pr-7, pr-11, pr-25, examples-rust |
| Swift | pr-9 |
| TypeScript/Bun | pr-26 |
| V | pr-2 |

Canonical source for merged entries is current upstream main. Open and closed heads are separate snapshots under `sources/pr-N-SHA/`; all source paths and script hashes are in `inventory.json`. Closed #14/#18/#21 are historical only. Official scores are separate fields from current source pins.

All 21 merged source trees match their PR-head submission trees except Rust #11 and #25, whose build.sh changed in upstream main. No source was modified by this preparation. ARM build planning was stopped after discovery of the completed official batch; no builds or local performance runs were executed for this update.
