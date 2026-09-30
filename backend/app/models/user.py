from pydantic import BaseModel
from typing import List

class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class UserUpdate(BaseModel):
    password: str | None = None
    role: str | None = None
    active: bool | None = None

class UserOut(BaseModel):
    id: str
    username: str
    role: str
    active: bool
    created_at: int
    cameras: List[str] = []

class LoginData(BaseModel):
    username: str
    password: str
