from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, true
from sqlalchemy.orm import Session as DbSession

from ..database import get_db
from ..deps import require_admin
from ..models import Application, AuditLog, User
from ..schemas import Overview, SystemSummary
from ..security import utcnow
from .applications import member_counts

router = APIRouter(prefix="/api/admin/overview", tags=["admin: overview"])


@router.get("", response_model=Overview)
def overview(db: DbSession = Depends(get_db), _: User = Depends(require_admin)):
    since = utcnow() - timedelta(hours=24)
    actions = dict(
        db.execute(
            select(AuditLog.action, func.count())
            .where(AuditLog.created_at >= since)
            .where(AuditLog.action.in_(["login", "login.failed", "sso.authorize", "sso.denied"]))
            .group_by(AuditLog.action)
        ).all()
    )
    counts = member_counts(db)
    apps = db.scalars(select(Application).order_by(Application.name)).all()
    return Overview(
        users_total=db.scalar(select(func.count(User.id))),
        users_active=db.scalar(select(func.count(User.id)).where(User.is_active == true())),
        admins=db.scalar(select(func.count(User.id)).where(User.is_admin == true())),
        systems_total=len(apps),
        sign_ins_24h=actions.get("login", 0),
        failed_sign_ins_24h=actions.get("login.failed", 0),
        sso_grants_24h=actions.get("sso.authorize", 0),
        denied_24h=actions.get("sso.denied", 0),
        systems=[
            SystemSummary(id=a.id, name=a.name, is_active=a.is_active, role_count=len(a.roles),
                          member_count=counts.get(a.id, 0))
            for a in apps
        ],
    )
