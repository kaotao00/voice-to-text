FROM python:3.12-slim
WORKDIR /app
COPY meeting-requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends libportaudio2 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r meeting-requirements.txt
COPY . .
ENV MEETING_HOME=/data PORT=8090 WHISPER_MODEL=base
VOLUME ["/data"]
EXPOSE 8090
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8090", "meeting_terminal:app"]
