#!/usr/bin/env bash
# Fake validate stage. Usage: fake_validate.sh <run_dir> <out_dir>
set -u
mkdir -p "$2"
echo "# validation" > "$2/validation.md"
echo "fake validate wrote $2/validation.md"
