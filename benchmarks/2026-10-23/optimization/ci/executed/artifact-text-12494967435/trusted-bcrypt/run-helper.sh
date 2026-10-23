#!/usr/bin/env bash
set -euo pipefail
cd "$VALIDATION_REPO/bench"
exec env GOWORK=off go run -mod=mod -modfile "$VALIDATION_BCRYPT_MODULE" "$VALIDATION_BCRYPT_HELPER" "$@"
