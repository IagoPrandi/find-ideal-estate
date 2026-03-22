#!/bin/bash
set -euo pipefail

Xvfb :99 -screen 0 1280x800x24 -ac &
export DISPLAY=:99

exec "$@"
