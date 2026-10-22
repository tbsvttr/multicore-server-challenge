#!/usr/bin/env bash
# Lab preparation, not submission code. Run only inside the owned combined app+PG container.
set -euo pipefail
REPO_ROOT=${REPO_ROOT:-/work}
EVIDENCE_ROOT=${EVIDENCE_ROOT:-/evidence}
APP_USER=${APP_USER:-challenge}
APP_UID=${APP_UID:-501}
APP_GID=${APP_GID:-501}
PHASE=${1:-install}
export PATH="/usr/local/go/bin:/usr/lib/postgresql/18/bin:$PATH"
mkdir -p "$EVIDENCE_ROOT/setup" "$EVIDENCE_ROOT/tools"

check_budget() {
  python3 - "$EVIDENCE_ROOT/setup/budget.json" <<'PY'
import json,pathlib,sys,platform
r=pathlib.Path('/sys/fs/cgroup')
def get(n):
 p=r/n
 return p.read_text().strip() if p.exists() else None
o={n:get(n) for n in ['cpu.max','memory.max','memory.swap.max','cpuset.cpus','cpuset.cpus.effective']}
o.update(platform=platform.platform(),architecture=platform.machine(),scope='app and PostgreSQL together; lab only')
pathlib.Path(sys.argv[1]).write_text(json.dumps(o,indent=2)+'\n')
quota,period=o['cpu.max'].split()
assert quota!='max' and int(quota)==8*int(period),o
assert o['memory.max']==str(16*1024**3),o
assert o['memory.swap.max']=='0',o
assert o['cpuset.cpus']=='', 'Explicit CPU affinity is forbidden: '+str(o)
PY
}

install_pg() {
  [ "$(id -u)" = 0 ] || { echo 'installation requires container root' >&2; exit 1; }
  [ "$(. /etc/os-release; echo "$ID:$VERSION_ID")" = ubuntu:24.04 ] || {
    echo 'expected Ubuntu 24.04; refusing a mismatched platform' >&2; exit 1; }
  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
  # Prevent package scripts starting PG before the fixed configuration is installed.
  if [ -e /usr/sbin/policy-rc.d ]; then cp /usr/sbin/policy-rc.d "$EVIDENCE_ROOT/setup/policy-rc.d.before"; fi
  printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
  chmod 755 /usr/sbin/policy-rc.d
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg postgresql-common python3 jq sysstat
  install -d /usr/share/keyrings
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor --yes -o /usr/share/keyrings/multicore-pgdg.gpg
  printf 'deb [signed-by=/usr/share/keyrings/multicore-pgdg.gpg] https://apt.postgresql.org/pub/repos/apt noble-pgdg main\n' \
    > /etc/apt/sources.list.d/multicore-pgdg.list
  apt-get update -qq
  apt-get install -y -qq postgresql-18 postgresql-client-18
  pg_lsclusters -h | awk '$1==18 && $2=="main" {found=1} END {exit !found}' \
    || pg_createcluster 18 main --start-conf=manual
  install -d /etc/postgresql/18/main/conf.d
  # box/pg-conf.sh uses host nproc/MemTotal, which Docker does not virtualize.
  # Render its exact formula for the declared shared 8-CPU/16-GiB budget instead.
  cat > /etc/postgresql/18/main/conf.d/90-pgtune.conf <<'CONF'
# Lab rendering of unmodified box/pg-conf.sh formulas for 8 CPUs and 16 GiB.
max_connections = 100
shared_buffers = 4096MB
effective_cache_size = 12288MB
maintenance_work_mem = 1024MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 9709kB
huge_pages = try
min_wal_size = 1GB
max_wal_size = 4GB
max_worker_processes = 8
max_parallel_workers = 8
max_parallel_workers_per_gather = 4
max_parallel_maintenance_workers = 4
CONF
  cp /etc/postgresql/18/main/conf.d/90-pgtune.conf "$EVIDENCE_ROOT/setup/90-pgtune.conf"
  pg_ctlcluster 18 main start
  runuser -u postgres -- psql -Xq -v ON_ERROR_STOP=1 -d postgres \
    -c "ALTER ROLE postgres PASSWORD 'challenge-test-only'"
  if ! id "$APP_USER" >/dev/null 2>&1; then
    getent group "$APP_GID" >/dev/null || groupadd --gid "$APP_GID" "$APP_USER"
    useradd --uid "$APP_UID" --gid "$APP_GID" --create-home --shell /bin/bash "$APP_USER"
  fi
  [ "$(id -u "$APP_USER")" = "$APP_UID" ] || { echo 'application UID differs from mounted source owner' >&2; exit 1; }
  app_home=$(getent passwd "$APP_USER" | cut -d: -f6)
  install -d -o "$APP_UID" -g "$APP_GID" -m 755 "$app_home"
  dpkg-query -W -f='${Package}\t${Version}\n' postgresql-18 postgresql-client-18 libc6 gcc \
    > "$EVIDENCE_ROOT/setup/package-versions.tsv"
  runuser -u postgres -- psql -X -AtF $'\t' -d postgres -c \
    "SELECT name, setting, unit, source FROM pg_settings ORDER BY name" \
    > "$EVIDENCE_ROOT/setup/pg-settings.tsv"
  cp /etc/postgresql/18/main/pg_hba.conf "$EVIDENCE_ROOT/setup/pg_hba.conf"
  uname -a > "$EVIDENCE_ROOT/setup/uname.txt"
  cat /proc/meminfo > "$EVIDENCE_ROOT/setup/proc-meminfo.txt"
  go version > "$EVIDENCE_ROOT/setup/go-version.txt"
  ulimit -n > "$EVIDENCE_ROOT/setup/nofile.txt"
  sha256sum "$REPO_ROOT/box/pg-conf.sh" "$REPO_ROOT/seed/make-seed.sh" \
    "$REPO_ROOT/schema.sql" "$REPO_ROOT/test/run.sh" "$REPO_ROOT/WORKLOAD.md" \
    "$REPO_ROOT/bench/go.mod" "$REPO_ROOT/bench/go.sum" > "$EVIDENCE_ROOT/setup/upstream-sha256.txt"
}

seed_db() {
  export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres PGPASSWORD=challenge-test-only
  cd "$REPO_ROOT"
  if [ "$1" = dev ]; then bash seed/make-seed.sh --dev; else bash seed/make-seed.sh; fi
}

build_tools() {
  cd "$REPO_ROOT/bench"
  go build -trimpath -o "$EVIDENCE_ROOT/tools/conformance" ./cmd/conformance
  go build -trimpath -o "$EVIDENCE_ROOT/tools/loadgen" ./cmd/loadgen
  go test ./cmd/loadgen
  sha256sum "$EVIDENCE_ROOT/tools/conformance" "$EVIDENCE_ROOT/tools/loadgen" \
    > "$EVIDENCE_ROOT/setup/tool-sha256.txt"
}

check_budget
case "$PHASE" in
  install) install_pg ;;
  seed-dev) seed_db dev ;;
  seed-full) seed_db full ;;
  tools) build_tools ;;
  all) install_pg; build_tools; seed_db dev; seed_db full ;;
  *) echo 'usage: setup-container.sh install|tools|seed-dev|seed-full|all' >&2; exit 2 ;;
esac
