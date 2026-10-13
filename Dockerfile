# Duosave in a container: the site on 0.0.0.0:8765.
# The database and images are not baked in — docker-compose.yml mounts them from the host.
FROM python:3.14-slim

# System libraries for the ML stack:
#   libgomp1             — onnxruntime (OCR + embeddings)
#   libgl1, libglib2.0-0 — OpenCV: rapidocr resolves to the headless build today, but the
#                          regular opencv-python (older rapidocr) imports libGL/libglib too.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DUOSAVE_HOST=0.0.0.0

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

# Build metadata: declared after the dependency layer so a new commit does not invalidate
# the pip layer. The updater passes these as --build-arg (see duosave/updater.py); when they are
# empty — a plain `docker compose up -d --build` after `git pull` — the commit is read from the
# trimmed .git that COPY . . brings in (see .dockerignore and duosave/buildinfo.py).
ARG DUOSAVE_COMMIT=""
ARG DUOSAVE_COMMIT_DATE=""
ARG DUOSAVE_VERSION=""
ARG DUOSAVE_CREATED=""
ENV DUOSAVE_COMMIT=${DUOSAVE_COMMIT} DUOSAVE_COMMIT_DATE=${DUOSAVE_COMMIT_DATE}
LABEL org.opencontainers.image.source="https://github.com/northis/duosave" \
      org.opencontainers.image.revision="${DUOSAVE_COMMIT}" \
      org.opencontainers.image.version="${DUOSAVE_VERSION}" \
      org.opencontainers.image.created="${DUOSAVE_CREATED}"

# Mount points used by docker-compose.yml: data/ (database, cache, crops, model) and image folders.
RUN mkdir -p data pictures screens screens_raw

# 8765 - site; 8766 - maintenance (published on the local network only).
EXPOSE 8765 8766

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/version', timeout=3)"

CMD ["python", "-m", "duosave", "serve"]
