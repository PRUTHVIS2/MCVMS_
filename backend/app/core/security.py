from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from app.config import config

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=1440) # 24h
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.auth.get("secret_key", "secret"), algorithm="HS256")
    return encoded_jwt

def decode_access_token(token: str) -> dict | None:
    try:
        decoded_token = jwt.decode(token, config.auth.get("secret_key", "secret"), algorithms=["HS256"])
        return decoded_token
    except jwt.PyJWTError:
        return None

fernet = Fernet(config.auth.get("fernet_key", Fernet.generate_key().decode()))

def encrypt_url(url: str) -> str:
    return fernet.encrypt(url.encode()).decode()

def decrypt_url(encrypted: str) -> str:
    return fernet.decrypt(encrypted.encode()).decode()
