from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
import sqlite3
from app.core.db import get_db
from app.core.security import verify_password, create_access_token
from app.core.audit import log_audit
from app.api.dependencies import get_current_user, rate_limit_login
from app.models.user import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", dependencies=[Depends(rate_limit_login)])
def login(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[sqlite3.Connection, Depends(get_db)]
):
    user = db.execute("SELECT * FROM users WHERE username = ?", (form_data.username,)).fetchone()
    if not user or not user["active"]:
        log_audit(None, "login_failed", form_data.username, {"reason": "not_found_or_inactive"})
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    if not verify_password(form_data.password, user["password_hash"]):
        log_audit(user["id"], "login_failed", user["username"], {"reason": "wrong_password"})
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    token = create_access_token(data={"sub": user["id"], "role": user["role"]})
    log_audit(user["id"], "login_success", user["username"])
    
    # httpOnly cookie for video player
    response.set_cookie(key="access_token", value=token, httponly=True, samesite="lax")
    
    return {"access_token": token, "token_type": "bearer"}

@router.post("/logout")
def logout(response: Response, current_user: Annotated[UserOut, Depends(get_current_user)]):
    response.delete_cookie("access_token")
    log_audit(current_user.id, "logout", current_user.username)
    return {"status": "ok"}

@router.get("/me", response_model=UserOut)
def get_me(current_user: Annotated[UserOut, Depends(get_current_user)]):
    return current_user
