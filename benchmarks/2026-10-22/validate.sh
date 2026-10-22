#!/usr/bin/env bash
# Runs the original CI path as a normal user, on dev or full seed, preserving output.
set -euo pipefail
REPO_ROOT=${REPO_ROOT:-/work}
EVIDENCE_ROOT=${EVIDENCE_ROOT:-/evidence}
APP_USER=${APP_USER:-challenge}
SUBMISSION=${SUBMISSION:-submissions/goose-native-tbsvttr}
TEMPLATE=${TEMPLATE:-conduit_dev}
export PATH="/usr/local/go/bin:/usr/lib/postgresql/18/bin:$PATH"
mkdir -p "$EVIDENCE_ROOT/conformance"
run_id="$(date -u +%Y%m%dT%H%M%SZ)-${TEMPLATE}-${SUBMISSION##*/}"
record="$EVIDENCE_ROOT/conformance/$run_id"
mkdir "$record"
printf '%s\n' "$SUBMISSION" > "$record/submission.txt"
printf '%s\n' "$TEMPLATE" > "$record/template.txt"
git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" rev-parse HEAD > "$record/upstream-head.txt"
find "$REPO_ROOT/$SUBMISSION" -type f ! -path '*/bin/*' ! -path '*/.goose/*' ! -path '*/.build/*' ! -path '*/.deps/*' ! -path '*/.goose-home/*' \
  -print0 | sort -z | xargs -0 sha256sum > "$record/source-sha256.txt"
cd "$REPO_ROOT"
set +e
runuser -u "$APP_USER" -- env PATH="$PATH" \
  PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres PGPASSWORD=challenge-test-only \
  TEMPLATE="$TEMPLATE" bash test/run.sh "$SUBMISSION" 2>&1 | tee "$record/output.log"
rc=${PIPESTATUS[0]}
set -e
printf '%s\n' "$rc" > "$record/exit-code.txt"
exit "$rc"
