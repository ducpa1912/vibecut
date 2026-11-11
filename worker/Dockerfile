FROM python:3.11-slim

# ffmpeg does the real probe, proxy, poster and render work. The Python package
# is installed from pyproject.toml, not a requirements.txt.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY duckclean_worker ./duckclean_worker
# `[ocr]` brings the ONNX OCR model used by /v1/detect. Without it the worker
# still runs and reports `ocr_unavailable` rather than inventing detections.
RUN pip install --no-cache-dir ".[ocr]"

ENV DUCKCLEAN_WORK_DIR=/tmp/duckclean \
    DUCKCLEAN_DEVICE_CLASS=cpu \
    PYTHONUNBUFFERED=1

RUN mkdir -p /tmp/duckclean

EXPOSE 7860

CMD ["uvicorn", "duckclean_worker.app:app", "--host", "0.0.0.0", "--port", "7860"]
