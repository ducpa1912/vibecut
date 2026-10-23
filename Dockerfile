FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIBECUT_HOST=0.0.0.0 \
    VIBECUT_PORT=8787 \
    VIBECUT_DATA=/data \
    VIBECUT_ENCODER=libx264 \
    VIBECUT_CAPTION_FONT_FILE=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

VOLUME ["/data"]
EXPOSE 8787

CMD ["python3", "app.py"]
