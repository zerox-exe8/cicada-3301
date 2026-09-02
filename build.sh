#!/usr/bin/env bash
set -e

echo "=== Installing dependencies for Kyro Discord Bot ==="

# Install system dependencies if root/apt is available
if command -v apt-get >/dev/null 2>&1; then
    echo "Updating apt repositories and installing libopus0 & ffmpeg..."
    apt-get update -y && apt-get install -y libopus0 libopus-dev ffmpeg || true
fi

# Install python requirements
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Build completed successfully ==="
