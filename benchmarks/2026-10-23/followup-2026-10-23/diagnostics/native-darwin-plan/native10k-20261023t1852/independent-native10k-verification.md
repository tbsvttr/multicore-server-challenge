# Independent native10k saved-file verification

PASS: 43 independent checks. This is completed diagnostic evidence only; it proves no capacity, stable gain, ranking, or client CPU headroom.

- SourceA app `7a7c31fbaedbb968` and Darwin client `c6053653c26c2136` match original frozen binaries, saved source manifests and build/conformance receipts. All36 app and17 native source files and all6 tools match.
- Exact10k protocol:60s ramp,120s measurement,15s tail, GOMAXPROCS2, all16 loopback destinations.
- Measured 316,229 requests; zero measured and recorded timeline errors; p95 8.359ms / p99 10.663ms. Native PASS and timing flags reproduce from saved data.
- Native box CPU remains N/A and client headroom remains unqualified; there is no hard client CPU/memory cap or capacity score.
- Saved actual client PID/UID501 and32768 soft/hard limits, actual app UID501/200000 limits, target8CPU/16GiB/no-swap conditions, observer coverage and owned stop/drop receipts verify.
- Both observer streams bracket measurement with complete clock/gap checks: target 201 samples and Darwin 200 samples.
- All 95 original checkpoint files remain unchanged. Their complete hashes are in the JSON receipt.

`backend-pids-related-only.log` retains only 3 Docker backend PID/path row(s). The full original process listing remains private and unchanged; its hash, size and line count are recorded in `backend-pids-redaction.json`. No benchmark error records were filtered or removed.

Only saved files were read. No live processes, Docker, SQL, networking, benchmark execution or active V4 phase data was accessed.

The proper charger and recovered charging state reported for this diagnostic are material confounds versus prior Linux P2. Charging, client resource controls and load were not matched. Moving the client outside the VM is not established as the cause of any improvement. This audit did not inspect or remeasure P2.
