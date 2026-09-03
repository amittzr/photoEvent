FROM python:3.11-slim

# Minimal runtime libs only — dlib is installed from a pre-built wheel below,
# so no C++ build toolchain is needed. libglib2.0-0 is required by Pillow.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dlib from a pre-built wheel (Python 3.11, Linux x86_64).
# This skips ~10 min C++ compilation and avoids build-tool dependencies.
# Wheel source: https://github.com/alvinregin/dlib-wheels (MIT-compatible).
RUN pip install --upgrade pip && \
    pip install https://github.com/alvinregin/dlib-wheels/releases/download/v20.0.0/dlib-20.0.0-cp311-cp311-linux_x86_64.whl

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
