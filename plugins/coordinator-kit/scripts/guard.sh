#!/usr/bin/env bash
# Guard hooks fail open: without a usable Python the tool call proceeds unguarded.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit 0
for coord_python in python3 python; do
  if command -v "$coord_python" >/dev/null 2>&1 && "$coord_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' </dev/null; then
    "$coord_python" -B "$script_dir/guard.py" "$@" || true
    exit 0
  fi
done
exit 0
