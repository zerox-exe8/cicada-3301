#!/bin/sh
set -e

echo "============================================================"
echo " Starting Kyro Core Distributed Engine & KyroLink Audio Node"
echo " Target Concurrency: C100K (100,000 Active Connections)"
echo " Environment: ${ENV:-production} | Worker: ${WORKER_ID:-worker-01}"
echo " Binding Port: ${PORT:-8000}"
echo "============================================================"

# C100K Kernel Optimization: Increase maximum open file descriptors if privileged
if [ "$(id -u)" = "0" ] || ulimit -n 1048576 2>/dev/null; then
    echo " [C100K TUNING] File descriptor limit (ulimit -n): $(ulimit -n)"
else
    echo " [C100K TUNING] Running with host file descriptor limit: $(ulimit -n)"
fi

# Execute CMD passed to container or default to python main.py
exec "$@"
