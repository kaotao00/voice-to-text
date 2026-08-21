# Docker Hub is often unavailable from mainland server networks; this is a
# compatible public mirror of the official Python image.
FROM docker.1panel.live/library/python:3.12-slim
WORKDIR /app
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends libportaudio2 \
    && rm -rf /var/lib/apt/lists/*
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
COPY meeting-requirements.txt .
RUN pip install --no-cache-dir -r meeting-requirements.txt
COPY . .
ENV MEETING_HOME=/data PORT=8090 WHISPER_MODEL=base
VOLUME ["/data"]
EXPOSE 8090
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8090", "meeting_terminal:app"]
