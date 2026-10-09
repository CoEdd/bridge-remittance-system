FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf

# OCR engine with Simplified Chinese data (English ships with tesseract-ocr), and a
# Chinese font with TrueType outlines that reportlab can embed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-chi-sim \
        fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# sentence-transformers needs torch. The CPU-only build avoids several GB of GPU libraries.
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements-ml.txt .
RUN pip install -r requirements-ml.txt

# Download the embedding model now, then forbid network lookups so the app runs offline.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# The small packages come last, so adding one does not repeat the large downloads above.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Run as an unprivileged user. /app/data is where the SQLite volume is mounted.
RUN useradd --create-home --uid 1000 bridge \
    && mkdir -p /app/data \
    && chown -R bridge:bridge /app
COPY --chown=bridge:bridge . .
USER bridge

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
