FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Optional trust anchors for networks that intercept TLS (corporate proxies,
# antivirus HTTPS scanning). Empty by default — see docker/ca-certificates/.
COPY docker/ca-certificates/ /usr/local/share/ca-certificates/
RUN update-ca-certificates

COPY requirements.txt .
RUN pip install --upgrade pip --cert /etc/ssl/certs/ca-certificates.crt \
    && pip install -r requirements.txt --cert /etc/ssl/certs/ca-certificates.crt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY pyproject.toml .

RUN pip install -e . --cert /etc/ssl/certs/ca-certificates.crt

CMD ["python", "-m", "app.main"]
