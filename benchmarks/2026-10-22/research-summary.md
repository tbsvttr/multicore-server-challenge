# Multicore challenge: rules and leader snapshot (2026-10-22)

Fetched read-only through gh CLI. Source files, all PR metadata, selected bodies/files/comments and architecture READMEs retained beside this report.

## What constitutes first place

Official current leaderboard: Rust Tokio Scooter1337, PR #7, **100,000 concurrent virtual users**, 26,279 req/s, p95 119ms, p99 185ms, zero errors, app20% / PG70% whole-box CPU. Maintainer comment dated2026-10-21 confirms same-box full-seed 5-minute hold. To take undisputed first, score above100,000 users in maintainer's official five-minute protocol; local throughput alone cannot update leaderboard.

Score protocol: fresh full seed per search; 3-minute low-load warmup; 60s ramp+60s measured probes doubling then bisection to5%; final60s ramp+300s measured hold, stepdown5% on fail. PASS requires combined p95<500ms,p99<1000ms,errors<1%. Generator-limited (>75% CPU or fell_behind) is invalid, never server ceiling. Measured latencies include failed requests,10s timeouts and a transparent idle-close retry. Probes/holds within search grow same DB; only fresh start resets it.

## Exact target and contract

Ubuntu24.04 x86_64;8dedicated vCPU/16GB total shared by app+PG18+(optionalNginx). No CPU affinity or host tuning. Fixed PG config/schema/indexes; max_connections100; app total95orless. DATABASE_URL,JWT_SECRET,HOST,PORT config. Direct-front preferred to save ~11% Nginx CPU, needs tens of thousands idleHTTP1.1 keepalive sockets (NOFILE200000); nginx mode idle>=65s. Health GET/api/tags200 within60s. Source-only pinned dependencies/install/build, no binaries; CI install.sh asroot then test/run.sh. Only submission folder may change. Front line required.

Fixed fullseed:100kusers,500karticles,5Mfavorites,2.5Mcomments,2Mfollows;~2.35GB. Devseed2% not adequate capacity evidence.19endpoints,197conformance steps; suite wins if spec differs. Thinktime7smean,session15minmean,~0.25rps/VU,~95%reads. Above100kVUs identities repeat; do not call them unique users.

No cross-request data/token/bcrypt result cache; each request reads livePG. Prepared statements/pools/HMAC key schedules okay. Every login bcryptcost10 againststoredhash, every JWT verifiesHS256+exp. Writes committed before response; no synchronous_commitoff. Groupcommit permitted onlywaitforcommit. No schema/serverconfig changes; sessionSET legal. AnySQL allowed ifsameanswers.

## Current optimization target

DB dominates70–80% boxCPU. Leading Rust uses2Tokio workers,6readconnections,2groupedwriteconnections,1bcryptworker4interleavedhashlanes. Compatible queuedreads coalesced inarray/LATERALquery(max32,no collectiondelay); repeatedpages share articlemetadata withinoneSQLexecution,viewer flagsperrequest. Tags waitingtogether shareexecutiononly. Pageidsfirst,boundedcounts1000, favoritecount+viewer membershiponescan, genericpreparedplans,jitoff,parallelqueryoff; committedgroupedwrites1mswindow max128; binaryJSONdirectencoding.

## New open Goose contender already exists

PR #31 XeonFX head43e0919ae5b693c1d3c1e8828b74bb774ef92ee0: ownGoose HTTP/epoll,PGwire+SCRAM,binaryresults,5lanebcrypt.4loops each3read+1writer PG;2hashers250mscollectionwindow; readbatch32/readhold1, listbatch+sharedenrichment portedfromRust7. Claims197conformance and6000read concurrent differential passes.

GCP c4-highcpu8 externaltwo matchingloadboxes freshfullseed60sramp+60smeasure:150kVUs39,653rps,p9520.3,p9955.6,zeroerrors;160k41,249rps,p95368,p99501 PASS;175k p95967 p992818 FAIL. **No five-minuteholds or scored warmup+grownDB run**, notofficialscore. Beforebatching ~130kceiling34krps; now160k41krps. Thisisimportant rival for future #1, not onlyofficialRust7.

## What Mac proves

Can compile and run unchanged197checks in Ubuntu24 ARM64/PG18, add dynamic/concurrency/fault tests, fullseed repeatable relative comparisons with app+PG shared8vCPU/16GiB. Arm64 and samehostloadgen mean labcomparisononly, not officialx86dedicated score. Loadgeneratorsneed ownbudgetandports: macOS ~16kephemeralports so<15kVUlocally; LinuxVM multiaddresses/generators required above64kconnections/targetIP:port. Do notpin submission or compare prior1CPU2GBSQLite/wrkbenchmarkasnewscore. To establish official#1 needmerge+maintainerbatch or access equivalentx86hostandexternalgenerators (notprovisionedwithoutspendauthorization).
