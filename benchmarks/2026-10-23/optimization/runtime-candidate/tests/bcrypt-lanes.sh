#!/usr/bin/env bash
# After build.sh: real Goose bcrypt lane differential, no database or server.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .build/goose.h && -x bin/conduit ]] || {
    echo 'Run build.sh before tests/bcrypt-lanes.sh.' >&2
    exit 1
}
goose_bin=${GOOSE_BIN:-"$PWD/.goose/build/goose"}
[[ -x $goose_bin ]] || { echo 'Set GOOSE_BIN to the compiler used by build.sh.' >&2; exit 1; }
goose_bin=$(readlink -f "$goose_bin")
goose_source=$(cd "$(dirname "$goose_bin")/.." && pwd)
[[ $("$goose_bin" version) == 'goose runtime df5f78ce88d4' ]] || {
    echo 'Expected the pinned Goose runtime df5f78ce88d4.' >&2; exit 1;
}
cmp "$goose_source/src/runtime/goose.h" .build/goose.h || {
    echo 'The test compiler runtime header must match build.sh output.' >&2; exit 1;
}
cc=${CC:-gcc}
out="$PWD/.build/bcrypt-lane-checks"
mkdir -p "$out"
cp tests/bcrypt-lanes.goose bcrypt.goose bcrypt_tables.goose sys.goose "$out/"
"$goose_bin" -O2 --standalone -o "$out/bcrypt-lanes.c" "$out/bcrypt-lanes.goose"
"$cc" -O3 -std=gnu11 -I.build -pthread "$out/bcrypt-lanes.c" native_sys.c -lm -pthread -o "$out/bcrypt-lanes"
"$out/bcrypt-lanes" | tee "$out/bcrypt-lanes.log"
