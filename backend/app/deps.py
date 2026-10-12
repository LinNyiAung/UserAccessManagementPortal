from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, update
from sqlalchemy.orm import Session as DbSession

from .config import settings
from .database import get_db
from .models import AuditLog, PortalSession, RefreshToken, User
from .security import hash_token, utcnow


def get_portal_session(request: Request, db: DbSession) -> PortalSession | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    session = db.get(PortalSession, hash_token(token))
    if not session or session.expires_at < utcnow() or not session.user.is_active:
        return None
    return session


def get_current_user(request: Request, db: DbSession = Depends(get_db)) -> User:
    session = get_portal_session(request, db)
    if not session:
        raise HTTPException(401, "Not authenticated")
    return session.user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Administrator access required")
    return user


def terminate_user_sessions(db: DbSession, user_id: int) -> None:
    """Global sign-out: kill the SSO session and stop systems from refreshing tokens."""
    db.execute(delete(PortalSession).where(PortalSession.user_id == user_id))
    db.execute(
        update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True)
    )


def audit(
    db: DbSession,
    actor: User | None,
    action: str,
    target: str = "",
    detail: str = "",
    request: Request | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            actor_username=actor.username if actor else None,
            action=action,
            target=target,
            detail=detail,
            ip=request.client.host if request and request.client else "",
        )
    )
