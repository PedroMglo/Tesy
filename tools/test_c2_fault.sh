#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

gcc-15 -O2 -Wall -Wextra -Werror -o tools/test_c2_fault tools/test_c2_fault.c
gcc-15 -shared -fPIC -O2 -Wall -Wextra -Werror -o tools/libc2_fault_pread.so tools/c2_fault_pread.c
fixture="$(mktemp results/c2-fault-fixture.XXXXXX)"
trap 'rm -f "$fixture"' EXIT
truncate -s 32768 "$fixture"

for mode in eio eof short delay; do
  output="$(TESY_C2_PREAD_FAULT="$mode" LD_PRELOAD="$PWD/tools/libc2_fault_pread.so" tools/test_c2_fault "$fixture" 2>&1)"
  [[ "$output" == *TESY_C2_FAULT_INJECTED* ]] || { echo "missing marker: $mode" >&2; exit 1; }
  case "$mode" in
    eio) [[ "$output" == *"read=-1 errno=5"* ]] ;;
    eof) [[ "$output" == *"read=0 errno=0"* ]] ;;
    short) [[ "$output" == *"read=4096 errno=0"* ]] ;;
    delay)
      [[ "$output" == *"read=16384 errno=0"* ]]
      delay_ms="${output##*elapsed_ms=}"
      (( delay_ms >= 180 ))
      ;;
  esac || { echo "unexpected injected result: $mode: $output" >&2; exit 1; }
  echo "$mode $output"
done
