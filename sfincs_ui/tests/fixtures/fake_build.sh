#!/usr/bin/env bash
# Fake build stage. Usage: fake_build.sh <run_dir>
# FAKE_SLEEP=<s>   wait before writing (default 0)
# FAKE_FAIL_BUILD=1  exit 1 without writing the model files
# FAKE_PARTIAL=1   write the model files but exit 1 (dies "after" writing)
set -u
run_dir="$1"
echo "fake build starting in $run_dir"
sleep "${FAKE_SLEEP:-0}"
if [[ "${FAKE_FAIL_BUILD:-0}" == "1" ]]; then echo "fake build failed" >&2; exit 1; fi
mkdir -p "$run_dir"
printf 'alpha           = 0.5\nhuthresh        = 0.05\n' > "$run_dir/sfincs.inp"
echo "0 0" > "$run_dir/sfincs.dep"
echo "fake build wrote model files"
if [[ "${FAKE_PARTIAL:-0}" == "1" ]]; then exit 1; fi
exit 0
