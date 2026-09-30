from fastapi import FastAPI
import logging
from contextlib import asynccontextmanager
import os
import ulid

from app.api import auth, users
from app.core.db import get_connection
from app.core.security import get_password_hash
from app.core.clock import Clock
from app.tools.migrate import migrate
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run migrations
    clock = Clock()
    migrate(clock)
    
    # Bootstrap owner
    conn = get_connection()
    owner_username = os.getenv("OWNER_USERNAME", "admin")
    owner_password = os.getenv("OWNER_PASSWORD", "admin")
    
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (owner_username,)).fetchone()
    if not existing:
        # Check if any owner exists
        any_owner = conn.execute("SELECT id FROM users WHERE role = 'owner'").fetchone()
        if not any_owner:
            user_id = str(ulid.ULID())
            pwd_hash = get_password_hash(owner_password)
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, owner_username, pwd_hash, 'owner', 1, clock.now_ms())
            )
            conn.commit()
            logger.info(f"Bootstrapped default owner: {owner_username}")
            
    yield

app = FastAPI(title="MCVMS", lifespan=lifespan)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok"}
