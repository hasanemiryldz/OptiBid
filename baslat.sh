#!/usr/bin/env sh
set -eu
cd -- "$(dirname -- "$0")"
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -B -X utf8 baslat.py "$@"
fi
exec python3 -B -X utf8 baslat.py "$@"
