#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for coord_python in python3 python; do
  if command -v "$coord_python" >/dev/null 2>&1 && "$coord_python" -c 'import sys,sqlite3; sys.exit(0 if sys.version_info >= (3,9) else 1)' </dev/null; then
    exec "$coord_python" "$script_dir/session_start.py"
  fi
done
printf '%s\n' 'Coordinator Kit migration requires Python 3.9+ with sqlite3. Install it and rerun bootstrap before coordinator dispatch.' >&2
exit 1
