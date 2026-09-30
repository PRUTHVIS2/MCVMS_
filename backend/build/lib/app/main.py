from fastapi import FastAPI
import logging
import asyncio
from contextlib import asynccontextmanager
import os
import ulid

from app.api import auth, users, cameras, ws
from app.core.db import get_connection
from app.core.security import get_password_hash, decrypt_url
from app.core.clock import Clock
from app.tools.migrate import migrate
from app.sources.rtsp import RTSPSource
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

active_sources = {}

async def camera_monitor():
    clock = Clock()
    while True:
        try:
            conn = get_connection()
            cams = conn.execute("SELECT id, rtsp_url_enc, enabled, status FROM cameras").fetchall()
            for cam in cams:
                if not cam["enabled"]:
                    if cam["id"] in active_sources:
                        active_sources[cam["id"]].stop()
                        del active_sources[cam["id"]]
                    continue
                
                if cam["id"] not in active_sources:
                    url = decrypt_url(cam["rtsp_url_enc"])
                    src = RTSPSource(url, clock, frozen_timeout=5.0)
                    src.start()
                    active_sources[cam["id"]] = src
                
                src = active_sources[cam["id"]]
                new_status = "online" if src.online else "offline"
                if new_status != cam["status"] and cam["status"] != "unknown": # keep unknown until first transition? No, update it immediately.
                    # Wait, if it just started it might be offline. Let's just update if different.
                    pass
                if new_status != cam["status"]:
                    conn.execute("UPDATE cameras SET status = ? WHERE id = ?", (new_status, cam["id"]))
                    conn.commit()
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        await asyncio.sleep(2)

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
            
    # Start monitor
    monitor_task = asyncio.create_task(camera_monitor())
    yield
    
    monitor_task.cancel()
    for src in active_sources.values():
        src.stop()

app = FastAPI(title="MCVMS", lifespan=lifespan)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(cameras.router, prefix="/api/v1")
app.include_router(ws.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
