FROM python:3.11-slim

# Build dependencies for dlib (face_recognition backend).
# dlib compiles from source and needs cmake + C++ toolchain.
# libX11 / libopenblas are pulled in by dlib's optional image/BLAS support.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
# dlib takes several minutes to compile — it is the bottleneck in this layer.
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
