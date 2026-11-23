# Targets used by dev.ps1 and compose.yaml: lock, runtime, test (all built on base).

# PIP_INDEX_URL installs uv itself. PYPI_FILES_MIRROR (optional) redirects the image's copy of
# uv.lock to a mirror before syncing; locking always uses the official index.
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PYPI_FILES_MIRROR=

FROM python:3.13-slim-trixie AS base

ARG PIP_INDEX_URL
ARG UV_VERSION=0.13.7

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN pip install --no-cache-dir --disable-pip-version-check --root-user-action=ignore \
        --index-url "$PIP_INDEX_URL" "uv==$UV_VERSION"
COPY scripts/mirror-lock.sh /usr/local/lib/mirror-lock.sh

WORKDIR /app


FROM base AS lock

COPY pyproject.toml uv.lock* ./
RUN uv lock


FROM base AS runtime

ARG PIP_INDEX_URL
ARG PYPI_FILES_MIRROR

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,id=ontology-uv-cache,target=/root/.cache/uv \
    sh /usr/local/lib/mirror-lock.sh && uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY src ./src
RUN --mount=type=cache,id=ontology-uv-cache,target=/root/.cache/uv uv sync --frozen --no-dev

RUN useradd --system --user-group --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/documents && chown app:app /data/documents
# A fresh named volume mounted here inherits the ownership above.
VOLUME ["/data/documents"]
USER app

# Trusted proxies come from the runtime environment (FORWARDED_ALLOW_IPS); uvicorn defaults to
# trusting 127.0.0.1 only.
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn ontology_platform.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]


FROM base AS test

ARG PIP_INDEX_URL
ARG PYPI_FILES_MIRROR

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,id=ontology-uv-cache,target=/root/.cache/uv \
    sh /usr/local/lib/mirror-lock.sh && uv sync --frozen --no-install-project
COPY alembic.ini ./
COPY src ./src
RUN --mount=type=cache,id=ontology-uv-cache,target=/root/.cache/uv uv sync --frozen
COPY scripts ./scripts
COPY tests ./tests

CMD ["bash", "scripts/check.sh"]
