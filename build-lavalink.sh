#!/usr/bin/env bash
# ==========================================
# Kyro - Lavalink node build script
# ==========================================
# Used by the dedicated Render Background Worker that runs the Lavalink node.
# The Discord bot itself does NOT need this - the bot service keeps using
# build.sh.
#
# Lavalink 4.2+ is mandatory: since March 2026 Discord only accepts
# end-to-end encrypted voice (DAVE) and Lavalink 4.2.0 was the first release
# that supports it.

set -e

LAVALINK_VERSION="4.2.2"
LAVALINK_DIR="${LAVALINK_DIR:-/app/lavalink}"

echo "=== Installing Java runtime for Lavalink ==="

if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y --no-install-recommends \
        default-jre-headless \
        ca-certificates \
        curl \
        fontconfig \
        libopus0 \
        ffmpeg \
        flac \
        || true
    rm -rf /var/lib/apt/lists/*
else
    echo "apt-get not available, assuming a JRE is already installed."
fi

java -version 2>&1 || { echo "FATAL: no Java runtime available."; exit 1; }

echo "=== Downloading Lavalink ${LAVALINK_VERSION} ==="

mkdir -p "${LAVALINK_DIR}"

if [ ! -f "${LAVALINK_DIR}/Lavalink.jar" ]; then
    curl -fsSL -o "${LAVALINK_DIR}/Lavalink.jar" \
        "https://github.com/lavalink-devs/Lavalink/releases/download/${LAVALINK_VERSION}/Lavalink.jar"
fi

# The youtube plugin is declared in application.yml, so Lavalink downloads it
# itself on the first boot. Pre-warming it here keeps the first real play from
# waiting on a plugin download.

echo "=== Lavalink ${LAVALINK_VERSION} ready in ${LAVALINK_DIR} ==="
ls -la "${LAVALINK_DIR}"
