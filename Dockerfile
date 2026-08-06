# ─── Stage 1: build the React SPA ────────────────────────────────────────────
FROM node:18-alpine AS frontend-build
WORKDIR /build

# Cache deps: copy manifests first, then install
COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile --network-timeout 600000

# Copy source and build. CI=false keeps ESLint warnings from failing the build.
COPY frontend/ ./
ENV CI=false \
    NODE_OPTIONS=--openssl-legacy-provider
RUN yarn build


# ─── Stage 2: FastAPI backend + compiled SPA ─────────────────────────────────
FROM python:3.11-slim AS runtime

# System deps for Pillow, cryptography, bcrypt, and the health probe
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libffi-dev libjpeg-dev zlib1g-dev libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (uses the already-pinned requirements.txt)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

# Backend source
COPY backend/ /app/backend/

# Compiled front-end (served by FastAPI StaticFiles at "/")
COPY --from=frontend-build /build/build/ /app/frontend/build/

# Runtime env — override any of these at deploy time
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    FRONTEND_BUILD_DIR=/app/frontend/build \
    PORT=8000

# Health probe used by both Docker and Amvera
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl --fail "http://localhost:${PORT}/health" || exit 1

EXPOSE 8000

# main.py imports the fully-wired FastAPI app from server.py, adds /health,
# and mounts the SPA at /. --proxy-headers lets Amvera's edge terminate TLS.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips=*"]
