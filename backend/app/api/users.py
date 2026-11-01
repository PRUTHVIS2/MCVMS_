import sqlite3
from typing import Annotated

import ulid
from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_owner
from app.core.audit import log_audit
from app.core.clock import Clock
from app.core.db import get_db
from app.core.security import get_password_hash
from app.models.user import UserCreate, UserOut

router = APIRouter(prefix="/users", tags=["users"])

@router.get("", response_model=list[UserOut])
def list_users(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_owner)]
):
    users = db.execute("SELECT * FROM users").fetchall()
    result = []
    for u in users:
        c_rows = db.execute("SELECT camera_id FROM user_cameras WHERE user_id = ?", (u["id"],)).fetchall()
        result.append(UserOut(
            id=u["id"],
            username=u["username"],
            role=u["role"],
            active=bool(u["active"]),
            created_at=u["created_at"],
            cameras=[r["camera_id"] for r in c_rows]
        ))
    return result

@router.post("", response_model=UserOut)
def create_user(
    user_in: UserCreate,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserOut, Depends(require_owner)]
):
    if user_in.role not in ('owner', 'admin', 'incharge'):
        raise HTTPException(status_code=422, detail="Invalid role")
        
    existing = db.execute("SELECT id FROM users WHERE username = ?", (user_in.username,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
        
    user_id = str(ulid.ULID())
    pwd_hash = get_password_hash(user_in.password)
    ts = Clock().now_ms()
    
    db.execute(
        "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, user_in.username, pwd_hash, user_in.role, 1, ts)
    )
    
    log_audit(current_user.id, "user_created", user_in.username, {"role": user_in.role})
    
    return UserOut(
        id=user_id,
        username=user_in.username,
        role=user_in.role,
        active=True,
        created_at=ts,
        cameras=[]
    )
