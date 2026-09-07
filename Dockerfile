# =============================================================================
# pulse-ep — production Docker image for the REST API + 3D viewer
# -----------------------------------------------------------------------------
# Two-stage build:
#
#   builder  → installs all wheels (incl. heavy native deps like VTK) into a
#              throw-away venv. Build deps stay out of the final image.
#   runtime  → minimal slim base + the venv from builder + a non-root user.
#
# Tag locally with:
#     docker build -t pulse-ep:dev .
# =============================================================================

ARG PYTHON_VERSION=3.12

# -----------------------------------------------------------------------------
# Stage 1 — builder
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# Some of the science wheels (VTK, lxml, pymeshfix) link against system
# libraries at runtime; the build itself uses prebuilt wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only the metadata first to get a cacheable dependency-install layer.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip wheel \
 && /opt/venv/bin/pip install ".[server,figures,sevenzip]"


# -----------------------------------------------------------------------------
# Stage 2 — runtime
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# Runtime shared libs needed by VTK/pyvista and psycopg2.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libgl1 \
        libosmesa6 \
        libglib2.0-0 \
        libxrender1 \
        libgomp1 \
        libpq5 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --shell /usr/sbin/nologin --uid 10001 pulse \
 && mkdir -p /var/lib/pulse-ep/reports /var/lib/pulse-ep/waveforms /var/lib/pulse-ep/drop \
 && chown -R pulse:pulse /var/lib/pulse-ep

COPY --from=builder /opt/venv /opt/venv

# The installed wheel supplies application code, templates and migrations.
WORKDIR /app

USER pulse

ENV PULSE_EP_HOST=0.0.0.0 \
    PULSE_EP_PORT=5000 \
    PULSE_EP_REPORTS_DIR=/var/lib/pulse-ep/reports

EXPOSE 5000

# gunicorn is the production WSGI runner; it imports the module-level
# `app` from pulse_ep.server.app. We still call init_db() ourselves on
# startup so the first hit doesn't pay a schema-creation tax.
CMD ["sh", "-c", "python -c 'from pulse_ep.core.database import init_db; init_db()' && exec gunicorn --bind ${PULSE_EP_HOST}:${PULSE_EP_PORT} --workers 2 --threads 4 --timeout 120 pulse_ep.server.app:app"]
