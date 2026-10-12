from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession

from ..database import get_db
from ..deps import require_admin
from ..models import AuditLog, User
from ..schemas import AuditOut

router = APIRouter(prefix="/api/admin/audit", tags=["admin: audit"])


@router.get("", response_model=list[AuditOut])
def list_audit(
    q: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    db: DbSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(AuditLog.action.ilike(like), AuditLog.target.ilike(like),
                              AuditLog.actor_username.ilike(like)))
    return [AuditOut.model_validate(e) for e in db.scalars(stmt).all()]
