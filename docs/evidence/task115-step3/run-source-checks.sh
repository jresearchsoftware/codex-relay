#!/usr/bin/env bash
# Run from the native Linux candidate checkout with Node 22 and Cargo 1.90.
set -euo pipefail
log_root=${1:?Pass an absolute log directory outside the candidate checkout}
mkdir -p "$log_root"
run() {
  local name=$1
  shift
  printf 'Running %s\n' "$name"
  if "$@" >"$log_root/$name.txt" 2>&1; then
    printf 'PASS %s\n' "$name"
    tail -n 10 "$log_root/$name.txt"
  else
    printf 'FAIL %s\n' "$name"
    tail -n 60 "$log_root/$name.txt"
    return 1
  fi
}
run diff-check git diff --check
run node-full npm test
run python-full python3 -m pytest -q deploy/tests deploy/ansible/tests
run rust-format cargo fmt --manifest-path reviewer/Cargo.toml --check
run rust-full cargo test --manifest-path reviewer/Cargo.toml --locked
run qualify python3 scripts/qualify.py
run candidate python3 scripts/check-candidate.py
