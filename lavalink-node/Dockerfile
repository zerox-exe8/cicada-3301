# ==========================================
# Kyro - Lavalink v4 audio node (Render Background Worker)
# ==========================================
# Lavalink 4.2+ is mandatory: since March 2026 Discord only accepts
# end-to-end encrypted voice (DAVE) and Lavalink 4.2.0 was the first release
# that supports it.
#
# The JVM heap is kept small on purpose: this node runs next to (or instead of)
# a small music bot, so a tight heap is enough and leaves memory for the bot.
# The youtube plugin is declared in application.yml and downloaded by Lavalink
# on the first boot.

FROM eclipse-temurin:21-jre-jammy

ENV LAVALINK_SERVER_PORT=2333 \
    LAVALINK_SERVER_ADDRESS=0.0.0.0 \
    JAVA_OPTS="-Xmx384m -XX:+UseG1GC -XX:MaxGCPauseMillis=100 -Dfile.encoding=UTF-8"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl fontconfig libopus0 ffmpeg flac \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/lavalink

ARG LAVALINK_VERSION=4.2.2

RUN curl -fsSL -o /opt/lavalink/Lavalink.jar \
        "https://github.com/lavalink-devs/Lavalink/releases/download/${LAVALINK_VERSION}/Lavalink.jar"

COPY application.yml /opt/lavalink/application.yml

EXPOSE 2333

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${LAVALINK_SERVER_PORT}/version" || exit 1

ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar /opt/lavalink/Lavalink.jar"]
