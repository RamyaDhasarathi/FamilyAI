FROM python:3.12-slim
WORKDIR /app
# OCR for photos of notices and scanned PDFs.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements.lock ./
COPY familyos ./familyos
# The versions the suite passed against (requirements.lock), not whatever is newest on the day of the build.
RUN pip install --no-cache-dir -c requirements.lock .
# Sealed originals: a directory the unprivileged user can write (the default, .blobs under /app, belongs to root).
RUN mkdir -p /data/blobs && chown -R nobody /data
ENV FAMILYOS_BLOB_DIR=/data/blobs
USER nobody
EXPOSE 8000
CMD ["uvicorn", "familyos.main:app", "--host", "0.0.0.0", "--port", "8000"]
