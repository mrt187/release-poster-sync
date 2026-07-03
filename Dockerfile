FROM python:3.12-slim

ENV SUPERCRONIC_VERSION=v0.2.33
ENV SUPERCRONIC=supercronic-linux-amd64
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/${SUPERCRONIC}
ENV SUPERCRONIC_SHA1SUM=71b0d58cc53f6bd72cf2f293e09e294b79c666d8

RUN apt-get update && apt-get install -y --no-install-recommends curl ffmpeg fonts-dejavu-core tzdata \
    && curl -fsSLO "$SUPERCRONIC_URL" \
    && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
    && chmod +x "$SUPERCRONIC" \
    && mv "$SUPERCRONIC" /usr/local/bin/supercronic \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync.py entrypoint.sh ./
RUN chmod +x entrypoint.sh \
    && ffmpeg -f lavfi -i color=c=black:s=320x180:d=1 -c:v libx264 -pix_fmt yuv420p /app/dummy.mp4 \
    && useradd -r -u 1000 -d /app appuser \
    && mkdir -p /posters && chown -R appuser:appuser /app /posters

USER appuser
VOLUME ["/posters"]
ENTRYPOINT ["./entrypoint.sh"]
