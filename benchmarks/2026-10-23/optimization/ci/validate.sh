#!/usr/bin/env bash
# Fork-only correctness validation. Run as the normal Ubuntu24 x86 runner user.
set -euo pipefail
submission=submissions/goose-native-tbsvttr
source_ref=${SOURCE_REF:-submissions/goose-native-tbsvttr}
out=${VALIDATION_OUT:-"${RUNNER_TEMP:-/tmp}/goose-optimized-validation"}
while (($#)); do
    case "$1" in
        --submission) submission=$2; shift 2 ;;
        --source-ref) source_ref=$2; shift 2 ;;
        --out) out=$2; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
repo=${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}
cd "$repo"
[[ $submission == submissions/* && $submission != *..* && $submission != /* ]]
[[ $source_ref =~ ^[A-Za-z0-9][A-Za-z0-9_./-]*$ ]]
[[ $(id -u) != 0 && $(uname -m) == x86_64 ]]
submission=$(realpath "$submission")
[[ $submission == "$repo"/submissions/* && -f $submission/build.sh ]]
relative=${submission#"$repo"/}
helpers="$repo/.github/validation-goose"
mkdir -p "$out"
out=$(realpath "$out")
printf '%s\n' 'Correctness only; this runner is not official challenge hardware.' > "$out/SCOPE.txt"
git fetch --no-tags origin "$source_ref"
source_commit=$(git rev-parse FETCH_HEAD)
export VALIDATION_SOURCE_COMMIT="$source_commit" VALIDATION_SUBMISSION="$relative" VALIDATION_OUT="$out"
python3 - <<'PY'
import json, os, pathlib, subprocess
run=lambda *a: subprocess.check_output(a,text=True).strip()
source=os.environ['VALIDATION_SOURCE_COMMIT']; sub=os.environ['VALIDATION_SUBMISSION']
head=run('git','rev-parse','HEAD')
source_tree=run('git','rev-parse',source+':'+sub)
head_tree=run('git','rev-parse','HEAD:'+sub)
assert source_tree==head_tree, 'validation branch submission differs from PR source'
changes=run('git','diff','--name-status',source,'HEAD').splitlines()
for change in changes:
    status,path=change.split('\t',1)
    assert status=='A' and (path=='.github/workflows/goose-optimized-validation.yml' or path.startswith('.github/validation-goose/')), change
out=pathlib.Path(os.environ['VALIDATION_OUT'])
(out/'source-equivalence.json').write_text(json.dumps({'source_commit':source,'validation_commit':head,
    'submission':sub,'source_tree':source_tree,'validation_tree':head_tree,'identical_submission_tree':True,
    'only_added_validation_files':True,'added_paths':changes},indent=2)+'\n')
PY
{ uname -a; id; nproc; free -m; go version; gcc --version | head -1; psql --version; } > "$out/host.txt"
psql -X -qAt -v ON_ERROR_STOP=1 -d postgres -c 'SHOW server_version' > "$out/postgres-version.txt"
[[ $(cat "$out/postgres-version.txt") == 18.* ]]
sha256sum seed/make-seed.sh schema.sql test/run.sh bench/cmd/conformance/golden-dev.jsonl > "$out/original-harness-sha256.txt"
stages="$out/stages.tsv"
: > "$stages"
declare -a server_pids=() databases=()
finish_status=FAIL

stage() {
    local name=$1
    shift
    set +e
    "$@" 2>&1 | tee "$out/$name.log"
    local codes=("${PIPESTATUS[@]}")
    set -e
    local rc=${codes[0]}
    if ((rc == 0 && codes[1] != 0)); then rc=${codes[1]}; fi
    printf '%s\t%s\n' "$name" "$rc" >> "$stages"
    return "$rc"
}
server_running() {
    local pid=$1 state
    kill -0 "$pid" 2>/dev/null || return 1
    state=$(ps -o stat= -p "$pid" 2>/dev/null) || return 0
    state=${state//[[:space:]]/}
    [[ $state != Z* ]]
}
terminate_server() {
    local pid=$1 mode=TERM i
    kill -TERM -- "-$pid" 2>/dev/null || true
    for i in {1..30}; do
        server_running "$pid" || break
        sleep .1
    done
    if server_running "$pid"; then
        mode=KILL
        kill -KILL -- "-$pid" 2>/dev/null || true
        for i in {1..20}; do
            server_running "$pid" || break
            sleep .1
        done
    fi
    if server_running "$pid"; then
        printf '%s\tFAILED_AFTER_KILL\n' "$pid" >> "$out/server-shutdown.tsv"
        return 1
    fi
    wait "$pid" 2>/dev/null || true
    printf '%s\t%s\n' "$pid" "$mode" >> "$out/server-shutdown.tsv"
}
stop_server() {
    local pid=$1 i
    terminate_server "$pid"
    for i in "${!server_pids[@]}"; do
        if [[ ${server_pids[i]} == "$pid" ]]; then server_pids[i]=0; fi
    done
}
drop_db() {
    local db=$1 i
    timeout 20s psql -X -q -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS $db WITH (FORCE)"
    for i in "${!databases[@]}"; do
        if [[ ${databases[i]} == "$db" ]]; then databases[i]=''; fi
    done
}
cleanup() {
    local rc=$? pid db
    trap - EXIT
    set +e
    for pid in "${server_pids[@]}"; do
        if [[ $pid != 0 ]]; then terminate_server "$pid" || rc=1; fi
    done
    for db in "${databases[@]}"; do
        if [[ -n $db ]]; then
            timeout 20s psql -X -q -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS $db WITH (FORCE)" || rc=1
        fi
    done
    VALIDATION_STATUS="$finish_status" VALIDATION_EXIT="$rc" python3 - <<'PY'
import hashlib,json,os,pathlib,subprocess
out=pathlib.Path(os.environ['VALIDATION_OUT']); sub=pathlib.Path(os.environ['VALIDATION_SUBMISSION'])
files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p.name!='receipt.json'}
exit_code=int(os.environ['VALIDATION_EXIT'])
receipt={'status':'PASS' if os.environ['VALIDATION_STATUS']=='PASS' and exit_code==0 else 'FAIL','exit':exit_code,
  'scope':'Clean native x86 source-build and correctness only; no capacity or performance claim.',
  'source_commit':os.environ['VALIDATION_SOURCE_COMMIT'],'source_tree':subprocess.check_output(['git','rev-parse','HEAD:'+str(sub)],text=True).strip(),
  'stages':[dict(name=n,exit=int(c)) for n,c in (line.split('\t') for line in (out/'stages.tsv').read_text().splitlines())],
  'artifact_sha256':files}
binary=sub/'bin/conduit'
if binary.exists(): receipt['candidate_binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
    exit "$rc"
}
trap cleanup EXIT

make_db() {
    local suffix=$1 template=${2:-conduit_seed}
    db_name="mc_pair_ci_${GITHUB_RUN_ID:-local}_${GITHUB_RUN_ATTEMPT:-1}_$suffix"
    [[ $db_name =~ ^[a-z][a-z0-9_]+$ && ${#db_name} -le 63 ]]
    psql -X -q -v ON_ERROR_STOP=1 -d postgres -c "CREATE DATABASE $db_name TEMPLATE $template STRATEGY FILE_COPY"
    databases+=("$db_name")
}
start_server() {
    local name=$1 dir=$2 db=$3 port=$4
    shift 4
    local dbhost=${PGHOST:-127.0.0.1}
    if [[ $dbhost == /* ]]; then dbhost=127.0.0.1; fi
    local app_url="postgres://conduit:conduit@$dbhost:${PGPORT:-5432}/$db"
    (ulimit -n 200000; exec setsid env DATABASE_URL="$app_url" JWT_SECRET="$JWT_SECRET" HOST=127.0.0.1 PORT="$port" "$@" bash "$dir/start.sh") > "$out/$name-server.log" 2>&1 &
    server_pid=$!
    server_pids+=("$server_pid")
    for _ in {1..60}; do
        if curl --max-time 2 -fsS -o /dev/null "http://127.0.0.1:$port/api/tags"; then
            ps -o pid=,euid=,pgid=,comm= -p "$server_pid" > "$out/$name-process.txt"
            [[ $(awk '/^Uid:/ {print $2}' "/proc/$server_pid/status") != 0 ]]
            cat "/proc/$server_pid/limits" > "$out/$name-limits.txt"
            return
        fi
        kill -0 "$server_pid" 2>/dev/null || { cat "$out/$name-server.log"; return 1; }
        sleep 1
    done
    echo "Server $name never became healthy" >&2
    return 1
}
fixture_url() {
    # Public CI service credentials; never used as the application's role.
    printf 'postgres://postgres:postgres@127.0.0.1:%s/%s' "${PGPORT:-5432}" "$1"
}

export BUILD_JOBS=${BUILD_JOBS:-2} CC=gcc PGCONNECT_TIMEOUT=5
unset GOOSE_BIN GOOSE_HOME
[[ ! -e $submission/.goose && ! -e $submission/.build && ! -e $submission/bin ]]
stage dependencies sudo bash "$submission/install.sh"
stage clean-build bash "$submission/build.sh"
[[ $(cat "$submission/.goose/COMMIT") == f605b5a07dd2aa3a5cb3f4c9b14002bd3c9d3d1a ]]
export GOOSE_BIN="$submission/.goose/build/goose"
"$GOOSE_BIN" version > "$out/goose-version.txt"
sha256sum "$submission/.deps/goose-f605b5a07dd2aa3a5cb3f4c9b14002bd3c9d3d1a.tar.gz" > "$out/goose-archive-sha256.txt"
[[ $(cut -d' ' -f1 "$out/goose-archive-sha256.txt") == 86482df9e11ff9472d2214e93a71cd7f22b05d31260f66d7e760d5df784a7e92 ]]
stage seed-dev bash seed/make-seed.sh --dev
grep -F 'OK: conduit_dev matches the reference seed' "$out/seed-dev.log"
stage conformance-dev bash test/run.sh "$submission"
stage native bash "$submission/tests/native.sh"
stage bcrypt-lanes bash "$submission/tests/bcrypt-lanes.sh"
cp -a "$submission/.build/native-checks" "$out/native-checks"
cp -a "$submission/.build/bcrypt-lane-checks" "$out/bcrypt-lane-checks"
python3 - "$out" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); native=json.loads((p/'native-checks/native.json').read_text()); pipe=json.loads((p/'native-checks/pipe-reply.json').read_text())
assert native['status']==pipe['status']=='PASS' and native['checks']+pipe['checks']==293966
assert 'PASS: 4000 Goose JWT assertions' in (p/'native-checks/jwt-ffi.log').read_text()
assert 'PASS: 252 exact-lane bcrypt comparisons' in (p/'bcrypt-lane-checks/bcrypt-lanes.log').read_text()
PY
stage seed-full bash seed/make-seed.sh
grep -F 'OK: conduit_seed matches the reference seed' "$out/seed-full.log"
stage conformance-full env TEMPLATE=conduit_seed bash test/run.sh "$submission"
stage conformance-full-features env TEMPLATE=conduit_seed WORKERS=1 PG_READERS=3 READ_BATCH=32 READ_HOLD=1 READ_BATCH_US=5000 WRITE_BATCH_US=1000 ARTICLE_BATCH=1 bash test/run.sh "$submission"
stage conformance-full-selected env TEMPLATE=conduit_seed WORKERS=2 PG_READERS=3 HASHERS=2 READ_BATCH=32 READ_HOLD=1 READ_BATCH_US=5000 WRITE_BATCH_US=1000 ARTICLE_BATCH=1 bash test/run.sh "$submission"

baseline_commit=3e9087473da5c56d5800ae9ee00ac1e84c44a135
baseline="$out/stock-source"
mkdir -p "$baseline"
if ! git cat-file -e "$baseline_commit^{commit}" 2>/dev/null; then
    git fetch --no-tags origin "$baseline_commit"
fi
git archive "$baseline_commit" "$relative" | tar -x -C "$baseline"
baseline="$baseline/$relative"
stage stock-build bash "$baseline/build.sh"
sha256sum "$baseline/bin/conduit" "$submission/bin/conduit" > "$out/comparison-binaries-sha256.txt"
export JWT_SECRET=multicore-server-challenge
make_db reads
read_db=$db_name
start_server stock "$baseline" "$read_db" 3101 WORKERS=1 PG_READERS=3 HASHERS=2 READ_BATCH=32 READ_HOLD=1 ARTICLE_BATCH=0
stock_pid=$server_pid
start_server candidate "$submission" "$read_db" 3102 WORKERS=1 PG_READERS=3 HASHERS=2 READ_BATCH=32 READ_HOLD=1 READ_BATCH_US=5000 WRITE_BATCH_US=1000 ARTICLE_BATCH=0
candidate_pid=$server_pid
stage read-batches python3 "$helpers/read-batches.py" --baseline http://127.0.0.1:3101 --candidate http://127.0.0.1:3102 --database-url "$(fixture_url "$read_db")" --out "$out/read-batches.json"
stop_server "$stock_pid"; stop_server "$candidate_pid"; drop_db "$read_db"

make_db quiet conduit_dev
quiet_db=$db_name
for us in 500000 0; do
    start_server "quiet-$us" "$submission" "$quiet_db" 3103 WORKERS=1 PG_READERS=3 READ_BATCH=32 READ_HOLD=1 READ_BATCH_US="$us" WRITE_BATCH_US=1000 ARTICLE_BATCH=0
    quiet_pid=$server_pid
    stage "quiet-$us" python3 "$helpers/quiet-read-timer.py" --base http://127.0.0.1:3103 --database-url "$(fixture_url "$quiet_db")" --expected-us "$us" --out "$out/quiet-$us.json"
    stop_server "$quiet_pid"
done
drop_db "$quiet_db"

make_db writes conduit_dev
write_db=$db_name
start_server writer "$submission" "$write_db" 3104 WORKERS=1 PG_READERS=3 READ_BATCH=32 READ_HOLD=1 READ_BATCH_US=0 WRITE_BATCH_US=50000 ARTICLE_BATCH=0
writer_pid=$server_pid
export BASE=http://127.0.0.1:3104 DATABASE_URL="$(fixture_url "$write_db")"
stage runtime-writes python3 "$helpers/runtime-write-probe-v2.py" --out "$out/runtime-writes.json"
stage favorite-fresh python3 "$helpers/favorite-race-probe.py" --out "$out/favorite-fresh.json"
stop_server "$writer_pid"
start_server writer-selected "$submission" "$write_db" 3104 WORKERS=2 PG_READERS=3 HASHERS=2 READ_BATCH=32 READ_HOLD=1 READ_BATCH_US=5000 WRITE_BATCH_US=1000 ARTICLE_BATCH=1
writer_pid=$server_pid
stage article-update-fresh python3 "$helpers/article-update-race.py" --case all --out "$out/article-update-fresh.json"
trusted_dir="$out/trusted-bcrypt"
mkdir -p "$trusted_dir"
cp "$repo/bench/go.mod" "$trusted_dir/go.mod"
cp "$repo/bench/go.sum" "$trusted_dir/go.sum"
cat >> "$trusted_dir/go.sum" <<'SUM'
golang.org/x/crypto v0.58.0 h1:COkYLr4k7nDI4r6QtMML2AfzeIswWHAJthLS6K/M/54=
golang.org/x/crypto v0.58.0/go.mod h1:Xh+kl5A+M0gMiWDytH2Hhr5Z7WbNCpv/eB/EFgfSk+w=
SUM
(
    cd "$repo/bench"
    go mod edit -modfile "$trusted_dir/go.mod" -require=golang.org/x/crypto@v0.58.0
)
# Keep Go's original module files unchanged; the wrapper runs from the pinned
# bench module with a separate, version-pinned module/sum under the evidence dir.
export VALIDATION_REPO="$repo" VALIDATION_BCRYPT_MODULE="$trusted_dir/go.mod" VALIDATION_BCRYPT_HELPER="$helpers/bcrypt-passwords.go"
cat > "$trusted_dir/run-helper.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd "$VALIDATION_REPO/bench"
exec env GOWORK=off go run -mod=mod -modfile "$VALIDATION_BCRYPT_MODULE" "$VALIDATION_BCRYPT_HELPER" "$@"
SH
stage password-nul-interop python3 "$helpers/password-nul-probe.py" --out "$out/password-nul-interop.json" --go-helper bash "$trusted_dir/run-helper.sh"
python3 - "$out" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1])
for name in ['article-update-fresh','password-nul-interop']:
    result=json.loads((p/(name+'.json')).read_text())
    assert result['pass'] is True and result['implementation_correct'] is True, name
PY
stop_server "$writer_pid"; drop_db "$write_db"
git diff --exit-code "$source_commit" HEAD -- "$relative"
git diff --exit-code -- "$relative"
git diff --exit-code -- bench/go.mod bench/go.sum
finish_status=PASS
