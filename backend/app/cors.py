"""CORS for browser apps (single-page apps) that sign in directly with the portal.

Each system can list its "web origins" (Keycloak's term). Only those origins may call
the OIDC endpoints a browser app needs, and only those endpoints: the portal's own
/api/* stays same-origin.
"""

import time

from sqlalchemy import select, true
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .database import SessionLocal
from .models import Application

BROWSER_ENDPOINTS = (
    "/.well-known/openid-configuration",
    "/oauth/token",
    "/oauth/userinfo",
    "/oauth/revoke",
    "/oauth/jwks",
)
CACHE_SECONDS = 30

_cache: tuple[float, frozenset[str]] | None = None


def invalidate_origins_cache() -> None:
    """Call after a system's web origins change, so the change applies immediately."""
    global _cache
    _cache = None


def allowed_origins() -> frozenset[str]:
    global _cache
    if _cache and time.monotonic() - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    with SessionLocal() as db:
        rows = db.scalars(select(Application.web_origins).where(Application.is_active == true())).all()
    origins = frozenset(o for row in rows for o in (row or []))
    _cache = (time.monotonic(), origins)
    return origins


class WebOriginsCORS(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        if not origin or not request.url.path.startswith(BROWSER_ENDPOINTS):
            return await call_next(request)

        allowed = origin.lower() in allowed_origins()
        cors_headers = {
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
        }

        # Preflight: the browser asks before sending e.g. a POST with Authorization.
        if request.method == "OPTIONS" and "access-control-request-method" in request.headers:
            if not allowed:
                return Response(status_code=403, headers={"Vary": "Origin"})
            return Response(status_code=204, headers={
                **cors_headers,
                "Access-Control-Allow-Methods": "GET, POST",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Max-Age": "600",
            })

        response = await call_next(request)
        if allowed:
            response.headers.update(cors_headers)
        return response
