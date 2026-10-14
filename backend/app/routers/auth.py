"""Portal sign-in (cookie session). This session is what makes SSO work across systems."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..database import get_db
from ..deps import audit, get_current_user, get_portal_session, terminate_user_sessions
from ..models import Application, PortalSession, User
from ..schemas import ChangePasswordRequest, LoginRequest, MyApplication, UserOut
from ..security import burn_password_check, hash_password, hash_token, new_token, utcnow, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession = Depends(get_db)):
    login_name = body.username.strip()
    user = db.scalar(
        select(User).where(or_(User.username == login_name, User.email == login_name.lower()))
    )
    if user is None:
        burn_password_check(body.password)
    if user is None or not verify_password(body.password, user.password_hash) or not user.is_active:
        audit(db, None, "login.failed", target=login_name, request=request)
        db.commit()
        raise HTTPException(401, "Invalid username or password")

    token = new_token()
    db.add(
        PortalSession(
            id=hash_token(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(minutes=settings.session_ttl_minutes),
        )
    )
    user.last_login_at = utcnow()
    audit(db, user, "login", target=user.username, request=request)
    db.commit()

    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return UserOut.model_validate(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: DbSession = Depends(get_db)):
    session = get_portal_session(request, db)
    if session:
        audit(db, session.user, "logout", target=session.user.username, request=request)
        terminate_user_sessions(db, session.user_id)
        db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.post("/auth/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(400, "Choose a password different from the current one")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    audit(db, user, "user.password_changed", target=user.username, request=request)
    db.commit()


@router.get("/me/applications", response_model=list[MyApplication])
def my_applications(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    """The launchpad: systems the signed-in user has at least one role in."""
    by_app: dict[int, list[str]] = {}
    for role in user.roles:
        by_app.setdefault(role.application_id, []).append(role.name)
    if not by_app:
        return []
    apps = db.scalars(
        select(Application)
        .where(Application.id.in_(by_app), Application.is_active == true())
        .order_by(Application.name)
    ).all()
    return [
        MyApplication(
            id=a.id, name=a.name, description=a.description, home_url=a.home_url,
            roles=sorted(by_app[a.id]),
            permissions=user.permissions_in(a.id),
        )
        for a in apps
    ]
