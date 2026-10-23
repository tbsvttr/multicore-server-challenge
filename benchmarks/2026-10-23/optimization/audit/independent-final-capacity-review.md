# Independent capacity review

PASS 53/53; all three frozen-auditor reruns exactly reproduce prior results and complete raw-file SHA inventories.

No five-minute hold was started. Neither implementation has a capacity score, proven capacity advantage, or first-place result from these studies.

| Implementation | First study | v2 | v3 | Five-minute capacity | Correctness |
|---|---|---|---|---|---|
| Rust7 | Generator invalid | Generator invalid | Clock invalid | None | 197/197 PASS |
| Goose32 | Operator-interrupted; incomplete | Generator invalid | Clock invalid | None | 197/197 PASS |

All 12 started phases are retained. Generator-limited and clock-invalid phases are not failed server-capacity bounds. Native verdicts remain unchanged and separate from local qualification. All complete targets remained healthy without target OOM.

The valid Rust100,000-user result is only a 60-second probe: p95 7.403 ms, p99 29.999 ms, zero measured/timeline errors, 26,473.77 requests/s. There is no matched valid Goose 100k comparison or five-minute capacity score.

V3 whole-phase wall/monotonic discontinuities reach about 6,185 seconds for Rust and 2,249 seconds for Goose. The saved macOS diagnostic separately records actual maintenance sleep/dark wake at 8% battery. Raw clock records establish phase invalidity. Owned benchmark containers/PostgreSQL were stopped.

Goose retains its full-seed 197/197 correctness PASS. These infrastructure-invalid or interrupted measurements do not establish an application correctness failure.

Three preexport JSON/Markdown audit pairs are saved as `preexport-capacity-first-result.*`, `preexport-capacity-v2-result.*` and `preexport-capacity-v3-result.*`; exact paths and hashes appear in the JSON review.
