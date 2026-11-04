import logging
import re
from typing import Any
import requests

from app.core.security import decrypt_url

logger = logging.getLogger(__name__)

DEFAULT_MEDIAMTX_API = "http://localhost:9997"


def sanitize_path_name(name: str) -> str:
    """MediaMTX path names can only contain alphanumeric characters, underscore, dot, minus, slash."""
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)


class MediaMTXService:
    def __init__(self, api_url: str = DEFAULT_MEDIAMTX_API, timeout: float = 2.0):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def is_local_stream(self, rtsp_url: str) -> bool:
        """Check if stream is published locally into MediaMTX directly."""
        lower = rtsp_url.lower()
        return "localhost:8554" in lower or "127.0.0.1:8554" in lower

    def sync_camera(self, name: str, rtsp_url: str) -> bool:
        """Register or update an external RTSP camera as a source path in MediaMTX."""
        if self.is_local_stream(rtsp_url):
            logger.debug("Stream %s is local publisher stream; skipping MediaMTX path proxy", name)
            return True

        path_name = sanitize_path_name(name)
        add_url = f"{self.api_url}/v3/config/paths/add/{path_name}"
        patch_url = f"{self.api_url}/v3/config/paths/patch/{path_name}"

        payload = {"source": rtsp_url}

        try:
            resp = requests.post(add_url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                logger.info("Successfully registered camera '%s' with MediaMTX (path: %s)", name, path_name)
                return True
            if resp.status_code == 400:
                # Path likely already exists; update it via patch
                patch_resp = requests.patch(patch_url, json=payload, timeout=self.timeout)
                if patch_resp.status_code == 200:
                    logger.info("Successfully updated camera '%s' in MediaMTX (path: %s)", name, path_name)
                    return True
                logger.debug("MediaMTX patch returned status %s: %s", patch_resp.status_code, patch_resp.text)
            else:
                logger.debug("MediaMTX add path returned status %s: %s", resp.status_code, resp.text)
        except Exception as e:  # noqa: BLE001
            logger.debug("MediaMTX API unreachable or failed to sync camera '%s': %s", name, e)

        return False

    def remove_camera(self, name: str) -> bool:
        """Remove a camera path from MediaMTX."""
        path_name = sanitize_path_name(name)
        del_url = f"{self.api_url}/v3/config/paths/delete/{path_name}"
        try:
            resp = requests.delete(del_url, timeout=self.timeout)
            if resp.status_code == 200:
                logger.info("Successfully removed camera '%s' from MediaMTX (path: %s)", name, path_name)
                return True
            logger.debug("MediaMTX delete path returned status %s: %s", resp.status_code, resp.text)
        except Exception as e:  # noqa: BLE001
            logger.debug("MediaMTX API unreachable or failed to remove camera '%s': %s", name, e)
        return False

    def sync_all_cameras(self, conn: Any) -> int:
        """Sync all enabled cameras from DB into MediaMTX."""
        count = 0
        try:
            rows = conn.execute("SELECT name, rtsp_url_enc FROM cameras WHERE enabled = 1").fetchall()
            for r in rows:
                try:
                    name = r["name"]
                    rtsp_url = decrypt_url(r["rtsp_url_enc"])
                    if self.sync_camera(name, rtsp_url):
                        count += 1
                except Exception as inner_e:  # noqa: BLE001
                    logger.warning("Failed to decrypt or sync camera %s: %s", r["name"], inner_e)
        except Exception as e:  # noqa: BLE001
            logger.debug("Failed querying cameras for MediaMTX sync: %s", e)
        return count


mediamtx_service = MediaMTXService()

