"""Production entry point for Amvera Cloud (and any Docker host).

This is a thin wrapper around the FastAPI app defined in server.py — it:
  1. Imports the fully-wired `app` (routers, middleware, WebSocket already attached).
  2. Adds a plain `/health` endpoint at the app root (in addition to `/api/health`).
  3. Mounts the compiled React bundle at `/` when `frontend/build` exists so a
     single container serves both the API and the SPA.

The preview environment (Kubernetes ingress + supervisor) continues to run
`uvicorn server:app --port 8001` unchanged. In production this file is invoked
by uvicorn via the Dockerfile: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Import the fully-configured app instance. server.py already:
#   • includes the /api router (auth, users, chat, files, admin, i18n)
#   • configures CORS from CORS_ORIGINS env (defaults to *)
#   • mounts the /api/ws WebSocket endpoint
from server import app  # noqa: E402,F401


@app.get("/health", tags=["infra"])
def health() -> dict:
    """Amvera / load-balancer health probe."""
    return {"status": "ok"}


# ────────── Static SPA (only when a build exists) ──────────
# The Dockerfile copies the compiled React bundle into /app/frontend/build.
_STATIC_DIR = Path(os.environ.get("FRONTEND_BUILD_DIR", "/app/frontend/build"))

if _STATIC_DIR.exists() and (_STATIC_DIR / "index.html").exists():
    # /static and other asset paths under /
    app.mount(
        "/static",
        StaticFiles(directory=_STATIC_DIR / "static"),
        name="spa-static",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_router(full_path: str):
        # Never intercept API or WebSocket routes.
        if full_path.startswith(("api/", "api", "ws", "health")):
            # FastAPI will not reach here for /api/* because those routes are
            # registered first — this guard is defensive.
            raise RuntimeError("api routes should not fall through to SPA")
        # Try to serve a real file (e.g. /manifest.json, /favicon.ico, /robots.txt)
        candidate = _STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        # Otherwise fall back to index.html — client-side router takes over.
        return FileResponse(_STATIC_DIR / "index.html")


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, log_level="info")
