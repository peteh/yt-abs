FROM python:3.13-slim

WORKDIR /app

# system dependencies for yt-dlp optional features (ffmpeg, etc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
#    atomicparsley \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY README.md .
COPY src ./src

RUN pip install --no-cache-dir .

CMD ["yt-abs", "--config", "config.yml"]
