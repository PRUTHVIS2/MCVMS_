import time
from collections import defaultdict
from typing import Annotated, Generator
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import sqlite3
from app.core.db import get_connection, get_db
from app.core.security import decode_access_token
from app.models.user import UserOut

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[sqlite3.Connection, Depends(get_db)]
) -> UserOut:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or not row["active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    
    cameras_rows = db.execute("SELECT camera_id FROM user_cameras WHERE user_id = ?", (user_id,)).fetchall()
    cameras = [r["camera_id"] for r in cameras_rows]
    
    return UserOut(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        active=bool(row["active"]),
        created_at=row["created_at"],
        cameras=cameras
    )

def require_role(allowed_roles: list[str]):
    def role_checker(current_user: Annotated[UserOut, Depends(get_current_user)]):
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return current_user
    return role_checker

require_owner = require_role(["owner"])
require_admin = require_role(["owner", "admin"])
require_incharge = require_role(["owner", "admin", "incharge"])

login_attempts = defaultdict(list)

def rate_limit_login(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    login_attempts[ip] = [t for t in login_attempts[ip] if now - t < 60]
    if len(login_attempts[ip]) >= 5:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")
    login_attempts[ip].append(now)
