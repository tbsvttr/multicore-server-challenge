# Native Darwin client feasibility

An unchanged-source Darwin client is technically plausible and worth a small diagnostic. It is not a drop-in100k–160k solution at the current Mac limits. Installed Go is1.27.2/darwin-arm64; the loadgen already handles missing Linux/proc data and Darwin RSS units. No build was performed. Go supports current Darwin/arm64, and the inspected run/merge source has no Linux-only build requirement. [Go Darwin support](https://go.dev/wiki/Darwin).

The saved target has no published ports. [Docker documents](https://docs.docker.com/desktop/features/networking/) that published host connections pass through com.docker.backend into the VM. A native client therefore needs an explicitly configured replacement target, preserving app+PG8CPU/16GiB/no-swap/no-affinity and the original image/config. Sixteen localhost host ports can all forward to container3000; unchanged loadgen accepts comma-separated host:port targets. No IP aliases are needed.

Observed ephemeral range is49152–65535:16,384 ports per destination tuple. A single published port cannot support100k connections. Eight destinations give a theoretical131,072 tuples; sixteen give262,144 before retries/TIME_WAIT. Current TCP MSL is15s; preserve at least the existing65s drain and measure reuse/closure.

The tighter issue is descriptors: kern.maxfiles245,760, maxfilesperproc122,880, and53,657 global files were already open. Current global headroom is192,103. If each forwarded connection consumes one native-client and one backend-proxy host socket,100k adds about200k FDs and already exceeds that headroom. This is a planning estimate, not a measured proxy-FD count. Higher-load runs need validated host/backend FD limits or different networking/external load hardware. A5k–10k smoke can fit with a normal-user soft nofile such as32768; shell hard=unlimited does not remove the kernel ceiling.

Minimal sequence: finish P2/build activity; pin the unchanged source and modules; build a new Darwin artifact with Go1.27.2 and record its hash; review an owned replacement target with the loopback mappings; run only a small original-workload diagnostic first. Keep multiple native processes, explicit GOMAXPROCS and all lag/active/error/clock checks. Capture client and backend process CPU/RSS/FD evidence plus host memory/CPU pressure. Expand only after those gates pass, under a new predeclared configuration shared by Rust and Goose.

Linux/proc/stat CPU is N/A on Darwin. That must remain visible; native CPU75% headroom is not thereby proved. An external observer is needed, and a Darwin process does not have the former Linux client8CPU/8GiB cgroup restriction. Use run/merge through an external driver rather than assuming the complete Linux search/monitor harness is portable.

This moves generator work out of the Linux VM scheduler while preserving the target budget. It still shares physical Mac CPU/RAM and introduces the Desktop forwarding path. It is a legitimate exploratory architecture, not proof of official dedicated-x86 rank or guaranteed removal of all generator/host bottlenecks. Static planning can proceed during P2; compilation should stay outside timed phases.

No network/container mutation, build, test or load was performed. Raw observed limits and the detailed conditional plan are in feasibility.json.
