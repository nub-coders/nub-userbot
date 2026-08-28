
FROM python:3.13.2-slim

# Set working directory
WORKDIR /app

# Runtime system dependencies. git is not only a build tool here: requirements.txt
# installs one dependency straight from a git URL, and `.update` shells out to
# `git pull --ff-only`.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libmagic1 \
    ffmpeg \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies. gcc and the libc headers are
# only needed to build the few wheels with no binary for this platform (TgCrypto
# has none for 3.13), so they are installed and removed inside a single layer --
# left in, the image would ship a compiler to production and hand anything that
# got code execution a way to build more.
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

# Create necessary directories. `state` is where the SQLite store goes when
# STORAGE_BACKEND=sqlite -- deliberately not `data/`, which ships the read-only
# word lists a volume mounted there would shadow.
RUN mkdir -p /app/downloads /app/temp /app/state

# Nothing here needs root, and the process holds a session that can act as the
# Telegram account -- so whatever gets in should not also arrive as uid 0. /app is
# handed over wholesale because plugins write scratch next to the code: per-user
# media directories, rendered stickers, downloaded thumbnails.
RUN useradd --create-home --uid 10001 userbot \
    && chown -R userbot:userbot /app
USER userbot

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Overridable, but the default must point at the volume rather than at the image
# layer, where the store would be discarded on every recreate.
ENV SQLITE_PATH=/app/state/sessions.db

# Run the userbot
CMD ["python", "main.py"]
