FROM python:3.13-slim

# Create a user and group
RUN groupadd -g 1000 appuser \
    && useradd -m -u 1000 -g appuser appuser

WORKDIR /app

# system dependencies for yt-dlp optional features (ffmpeg, etc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    # for m4a metadata editing: 
    atomicparsley \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY README.md .
COPY src ./src

RUN pip install --no-cache-dir .

# Switch to the new user
USER appuser

CMD ["yt-abs", "--config", "config.yml"]
