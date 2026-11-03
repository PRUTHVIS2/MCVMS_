import asyncio
import logging
import os
from contextlib import asynccontextmanager

import ulid
from dotenv import load_dotenv
from fastapi import FastAPI

from app.api import (
    actions,
    alerts,
    auth,
    calendar,
    cameras,
    events,
    templates,
    users,
    ws,
    zones,
)
from app.core.clock import Clock
from app.core.db import get_connection
from app.core.health import get_health_status
from app.core.security import decrypt_url, get_password_hash
from app.pipeline.analyzer import Analyzer
from app.pipeline.camera_runtime import (
    CameraRuntime,
    load_rules_for_camera,
    register_runtime,
    unregister_runtime,
)
from app.recorder.clipper import Clipper
from app.recorder.ffmpeg_recorder import FFmpegRecorder
from app.services.alerts import AlertService
from app.services.events import EventService
from app.sources.rtsp import RTSPSource
from app.tools.migrate import migrate
from app.vision.detector import Detector
from app.vision.tracker import Tracker

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

active_sources: dict[str, RTSPSource] = {}
active_runtimes_map: dict[str, CameraRuntime] = {}
active_recorders: dict[str, FFmpegRecorder] = {}

alert_service = AlertService()
clipper = Clipper()
event_service = EventService(alert_service=alert_service, clipper=clipper)
shared_detector: Detector | None = None


async def camera_monitor():
    global shared_detector
    clock = Clock()
    while True:
        try:
            conn = get_connection()
            cams = conn.execute(
                "SELECT id, name, rtsp_url_enc, enabled, status, width, height, fps FROM cameras"
            ).fetchall()
            cam_ids_in_db = {c["id"] for c in cams}

            # Stop and remove any cameras deleted from DB
            for cid in list(active_sources.keys()):
                if cid not in cam_ids_in_db:
                    if cid in active_runtimes_map:
                        rt = active_runtimes_map.pop(cid)
                        rt.stop()
                        unregister_runtime(cid)
                    if cid in active_recorders:
                        rec = active_recorders.pop(cid)
                        rec.stop()
                    src = active_sources.pop(cid)
                    src.stop()

            for cam in cams:
                cam_id = cam["id"]
                if not cam["enabled"]:
                    if cam_id in active_runtimes_map:
                        rt = active_runtimes_map.pop(cam_id)
                        rt.stop()
                        unregister_runtime(cam_id)
                    if cam_id in active_recorders:
                        rec = active_recorders.pop(cam_id)
                        rec.stop()
                    if cam_id in active_sources:
                        active_sources[cam_id].stop()
                        del active_sources[cam_id]
                    continue

                if cam_id not in active_sources:
                    try:
                        url = decrypt_url(cam["rtsp_url_enc"])
                    except Exception as e:  # noqa: BLE001
                        logger.error(f"Failed to decrypt RTSP URL for camera {cam_id}: {type(e).__name__} {e}")
                        continue
                    src = RTSPSource(url, clock, frozen_timeout=5.0, camera_id=cam_id)
                    src.start()
                    active_sources[cam_id] = src

                src = active_sources[cam_id]
                new_status = "online" if src.online else "offline"

                # Update camera dimensions and fps if stream is online and db lacks them
                if src.online and src.width and src.height:
                    if cam["width"] is None or cam["height"] is None or cam["fps"] is None:
                        conn.execute(
                            "UPDATE cameras SET width = ?, height = ?, fps = ? WHERE id = ?",
                            (src.width, src.height, src.fps, cam_id)
                        )
                        conn.commit()

                # Start analysis runtime and recorder once online
                if src.online:
                    if cam_id not in active_runtimes_map:
                        try:
                            if shared_detector is None:
                                shared_detector = Detector()
                            analyzer = Analyzer(
                                camera_id=cam_id,
                                source=src,
                                detector=shared_detector,
                                tracker=Tracker(fps=int(src.fps or 25))
                            )
                            rules, zones = load_rules_for_camera(cam_id, conn)
                            runtime = CameraRuntime(
                                camera_id=cam_id,
                                analyzer=analyzer,
                                event_service=event_service,
                                rules=rules,
                                zones=zones,
                                clipper=clipper,
                                clock=clock,
                                camera_name=cam["name"]
                            )
                            register_runtime(runtime)
                            runtime.start()
                            active_runtimes_map[cam_id] = runtime
                            logger.info(f"Started analysis runtime for camera {cam_id} ({cam['name']})")
                        except Exception as e:  # noqa: BLE001
                            logger.error(f"Failed to start CameraRuntime for {cam_id}: {e}", exc_info=True)

                    if cam_id not in active_recorders:
                        try:
                            url = decrypt_url(cam["rtsp_url_enc"])
                            rec = FFmpegRecorder(camera_id=cam_id, rtsp_url=url, clock=clock)
                            rec.start()
                            active_recorders[cam_id] = rec
                            logger.info(f"Started continuous recorder for camera {cam_id}")
                        except Exception as e:  # noqa: BLE001
                            logger.error(f"Failed to start FFmpegRecorder for {cam_id}: {e}", exc_info=True)
                    elif not active_recorders[cam_id].is_alive():
                        logger.warning(f"Recorder for camera {cam_id} stopped unexpectedly, restarting...")
                        active_recorders[cam_id].start()

                if new_status != cam["status"]:
                    now_ms = clock.now_ms()
                    conn.execute("UPDATE cameras SET status = ? WHERE id = ?", (new_status, cam_id))
                    conn.commit()

                    if new_status == "offline":
                        alert_service.raise_camera_offline(cam_id, cam_id, now_ms, conn)
                    elif new_status == "online":
                        alert_service.clear_camera_offline(cam_id, conn)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Monitor error: {type(e).__name__}: {e}", exc_info=True)
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Set event loop for WebSocket thread-safe broadcasts
    ws.manager.set_loop(asyncio.get_running_loop())

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
    for rt in list(active_runtimes_map.values()):
        try:
            rt.stop()
        except Exception:
            pass
    active_runtimes_map.clear()

    for rec in list(active_recorders.values()):
        try:
            rec.stop()
        except Exception:
            pass
    active_recorders.clear()

    for src in list(active_sources.values()):
        try:
            src.stop()
        except Exception:
            pass
    active_sources.clear()


app = FastAPI(title="MCVMS", lifespan=lifespan)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(cameras.router, prefix="/api/v1")
app.include_router(zones.router, prefix="/api/v1")
app.include_router(actions.router, prefix="/api/v1")
app.include_router(templates.router, prefix="/api/v1")
app.include_router(calendar.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(ws.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/system/health")
def system_health():
    return get_health_status().model_dump()
