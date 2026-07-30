# AutoUGC-TH backend image (API + Celery worker/beat share this image).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System deps: build tools for psycopg2, plus ffmpeg for the editing module.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Install the root/core requirements first (best cache layer).
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# 2) Copy the source tree.
COPY . /app

# 3) Modules declare their OWN deps via app/modules/<name>/requirements.txt.
#    Concatenate every fragment and install so a module never edits the root file.
#    (Runs at build time; safe if no fragments exist.)
RUN set -e; \
    frag=$(find /app/app/modules -mindepth 2 -maxdepth 2 -name requirements.txt 2>/dev/null || true); \
    if [ -n "$frag" ]; then \
        echo "Installing module requirement fragments:"; echo "$frag"; \
        cat $frag > /tmp/module-requirements.txt; \
        pip install -r /tmp/module-requirements.txt; \
    else \
        echo "No module requirement fragments found."; \
    fi

EXPOSE 8000

# Default command runs the API; docker-compose overrides it for worker/beat.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
