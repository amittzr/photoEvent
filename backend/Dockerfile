FROM python:3.11-slim

# Minimal runtime dependencies only — no C++ build tools needed because
# dlib is installed from a pre-built binary wheel below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dlib from a pre-built wheel — skips C++ compilation (~10 min saved).
# Wheel source: https://github.com/alvinregin/dlib-wheels (MIT-compatible).
RUN pip install --upgrade pip && \
    pip install https://github.com/alvinregin/dlib-wheels/releases/download/v20.0.0/dlib-20.0.0-cp311-cp311-linux_x86_64.whl

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
