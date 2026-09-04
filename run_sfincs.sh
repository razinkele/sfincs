#!/usr/bin/env bash
# Run the Linux build of SFINCS v2.4.0 Galibier on a model directory.
#
#   ./run_sfincs.sh [model_dir] [threads]
#
# model_dir  directory containing sfincs.inp (default: current directory)
# threads    OpenMP threads (default: $OMP_NUM_THREADS, else all cores)
#
# Output goes to sfincs_log.txt inside the model directory, mirroring the
# Windows run.bat convention from the SFINCS manual.
set -euo pipefail

SFINCS_BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sfincs-linux/bin/sfincs"
MODEL_DIR="${1:-.}"
THREADS="${2:-${OMP_NUM_THREADS:-$(nproc)}}"

[[ -x "$SFINCS_BIN" ]] || { echo "sfincs binary not found at $SFINCS_BIN" >&2; exit 1; }
[[ -f "$MODEL_DIR/sfincs.inp" ]] || { echo "no sfincs.inp in $MODEL_DIR" >&2; exit 1; }

cd "$MODEL_DIR"
echo "Running SFINCS in $(pwd) with $THREADS threads (log: sfincs_log.txt)"
OMP_NUM_THREADS="$THREADS" "$SFINCS_BIN" 2>&1 | tee sfincs_log.txt
