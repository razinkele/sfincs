#!/usr/bin/env bash
# Fake SFINCS solver: prints the real progress line format into sfincs.log in the cwd.
# FAKE_STEPS=<n>    progress lines (default 4)      FAKE_SLEEP=<s>  between lines (default 0.05)
# FAKE_FAIL_SIM=1   exit 3 before the finish line   FAKE_STUBBORN=1 ignore SIGTERM
set -u
exec >> sfincs.log 2>&1   # like the real solver: it writes its own sfincs.log in the cwd
if [[ "${FAKE_STUBBORN:-0}" == "1" ]]; then trap '' TERM; fi
echo "------------ Welcome to SFINCS ------------"
echo "threads=${OMP_NUM_THREADS:-unset}"
steps="${FAKE_STEPS:-4}"
for ((i=1; i<=steps; i++)); do
  pct=$(( i * 100 / steps ))
  printf '  %d%% complete,  %s s remaining ...\n' "$pct" "$(( steps - i ))"
  sleep "${FAKE_SLEEP:-0.05}"
done
if [[ "${FAKE_FAIL_SIM:-0}" == "1" ]]; then echo "fatal: fake failure"; exit 3; fi
: > sfincs_his.nc
echo "---------- Simulation finished -----------"
echo "----------- Closing off SFINCS -----------"
exit 0
