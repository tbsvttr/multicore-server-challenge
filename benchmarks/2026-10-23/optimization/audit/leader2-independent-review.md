# Independent static leader2 review

Reviewer: /root/query_plan_optimizer/runtime_gc_diagnostics, independent of the implementation author. Reviewed server SHA-256 eda6edd356e141b532d2db33a14aeed612956aa7a02e3327479f677563fc3c87 and patch SHA-256 8b55ea6f0afdf731e2da11825d7d5ccccf7ead429fb257da5a23421d69041808. No actionable finding.

- Ownership detaches before node/Conn reuse (server.goose:429); generation plus read_node checks protect stale references (435,443).
- Early disconnect release requires a locally queued readonly request (153). Submitted reads, batch followers, hash jobs and writes retain their owners.
- Oldest eligible direct/pooled-family heads compete after each admitted SQL execution (477), removing prior direct-priority and fixed-family starvation.
- Reader admission reserves at most four closed groups (340,303), each at most four executions (362): default bound 16 executions/512 batched HTTP requests per reader. Writer groups remain 64.
- Quiet pooled work retains the shared timer/gate (323,350); direct work flushes in the current event-loop iteration.
- READ_BATCH=0 routes reads through direct queue 8 (469,369), preserving reader caps while bypassing collection/READ_HOLD.
- Post-commit handlers replace saved mutations with readonly messages before queueing (routes.goose:433,453); delay cannot replay committed writes.

This is static review only. No build, queries, infrastructure access or source edits were performed by the reviewer. Compilation, conformance, targeted cap/fairness/disconnect probes and native measurement remain required before promotion. No causal explanation of the 110k collapse or performance gain is established.
