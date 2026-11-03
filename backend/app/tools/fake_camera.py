import argparse
import subprocess
import sys
from pathlib import Path

import cv2


def detect_file_fps(file_path: str) -> int:
    try:
        cap = cv2.VideoCapture(file_path)
        raw_fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if raw_fps and raw_fps > 0:
            return round(raw_fps)
    except (cv2.error, OSError):
        return 25
    return 25


def main():
    parser = argparse.ArgumentParser(description="Fake Camera RTSP stream loop")
    parser.add_argument("file", nargs="?", default=None, help="Video file to loop")
    parser.add_argument("--source", "--clip", dest="source_file", help="Video file to loop (alternative to positional argument)")
    parser.add_argument("--cam", "--camera", "--stream-name", dest="cam", default="cam01", help="Camera name in RTSP path (e.g. cam01 -> rtsp://localhost:8554/cam01)")
    parser.add_argument("--fps", type=int, default=None, help="Target FPS (default: auto-detected from video, fallback 25)")
    parser.add_argument("--bitrate", type=str, default="4M", help="Target video bitrate (default: 4M)")
    parser.add_argument("--loop", action="store_true", default=True, help="Loop indefinitely (enabled by default)")
    args = parser.parse_args()

    file_path = args.source_file or args.file
    if not file_path:
        parser.error("A video file must be provided either as positional argument or with --source")

    resolved_path = Path(file_path).resolve()
    if not resolved_path.exists():
        parser.error(f"Video file does not exist: {resolved_path}")

    target_fps = args.fps or detect_file_fps(str(resolved_path))
    bitrate = args.bitrate
    bufsize = f"{int(bitrate.rstrip('MkK')) * 2}M" if bitrate.endswith(("M", "m")) else "8M"

    url = f"rtsp://localhost:8554/{args.cam}"
    print(f"Starting fake camera stream from {resolved_path} to {url} (fps={target_fps}, bitrate={bitrate})")

    # Command configured for low-latency, zero-corruption RTSP streaming:
    # 1. -tune zerolatency: disables lookahead and B-frames so slices are transmitted in strict temporal order.
    # 2. -pix_fmt yuv420p: standard 8-bit 4:2:0 chroma subsampling for decoder compatibility.
    # 3. -b:v / -maxrate / -bufsize: prevents huge VBR spikes from overflowing MediaMTX's TCP buffers.
    # 4. -g <fps>: produces an IDR keyframe every 1 second for rapid decoder sync.
    cmd = [
        "ffmpeg",
        "-re",
        "-stream_loop", "-1",
        "-i", str(resolved_path),
        "-an",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-b:v", bitrate,
        "-maxrate", bitrate,
        "-bufsize", bufsize,
        "-g", str(target_fps),
        "-r", str(target_fps),
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        url
    ]

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nStopped by user")
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
