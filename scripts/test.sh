#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest -q
python -m compileall -q src tests
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
bash -n scripts/build_stock.sh
git diff --check
