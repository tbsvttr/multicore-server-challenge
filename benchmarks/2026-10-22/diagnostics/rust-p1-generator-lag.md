# Corrected Rust arm1: generator lag diagnosis

Native INVALID_GENERATOR is retained. The generator’s66.8% average quota utilization hid a burst near the ramp/measurement boundary: roughly95–101% of its two-CPU quota at t54–67. Between the actual measured monitor endpoints (t60.112–119.237),79of591 quota periods throttled, accumulating21.175s of task-throttled time. This counter is cumulative across tasks, not21s of whole-box wall pause. The target recorded zero CPU quota throttling.

Shard0 scheduled sampler callbacks t58–61 all ran around actual t62.807; shard2 around62.588; shard1’s t60 callback ran at62.312. Thus the backlog began late in ramp and reached the first measured seconds. Native boxStats checks t60–119 and correctly flagged measured callbacks above500ms. Tail maxima were only1.55/2.26/1.71/1.58ms. Three shards were native LG-limited; shard3 was not. All80k users met the99% active threshold and no request errors occurred, but native latency SLOs also failed.

The independent load/target monitors remained near1Hz (maximum gaps1.057/1.011s), with maximum wall/monotonic step disagreement17.7ms. This does not support a multi-second whole-VM pause or clock jump. Host observations showed compression/swap-in activity, no new swapouts; guest load memory pressure and OOM counters remained zero. Host contention may contribute, but does not identify a unique cause. No GC trace or per-process scheduler profile was collected, so the exact runtime cause is unproven.

No trial was excluded anew, replaced, trimmed or rescored; no generator, app, protocol or running study was changed by this analysis.
