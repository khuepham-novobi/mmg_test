# MMG QA platform — FastAPI runner + Playwright/Chromium.
# Mirrors D:\project\dto\test\qa-platform\Dockerfile.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# --- python deps -------------------------------------------------------
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt

# --- Chromium + its OS libraries ---------------------------------------
# --with-deps pulls the apt packages Chromium needs (fonts, nss, X libs).
# Baked in so no browser download happens at run time.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
EXPOSE 7200

# Bind outside the container. The port is passed here rather than in
# config/local.yaml because backend/config.py reads it at import time.
ENV RUNNER_HOST=0.0.0.0 \
    RUNNER_PORT=7200

CMD ["python", "run_server.py"]
