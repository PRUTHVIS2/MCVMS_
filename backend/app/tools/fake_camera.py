import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Fake Camera RTSP stream loop")
    parser.add_argument("file", nargs="?", default=None, help="Video file to loop")
    parser.add_argument("--source", dest="source_file", help="Video file to loop (alternative to positional argument)")
    parser.add_argument("--cam", "--camera", dest="cam", default="cam01", help="Camera name in RTSP path (e.g. cam01 -> rtsp://localhost:8554/cam01)")
    parser.add_argument("--fps", type=int, default=25, help="Target FPS")
    parser.add_argument("--loop", action="store_true", default=True, help="Loop indefinitely (enabled by default)")
    args = parser.parse_args()
    
    file_path = args.source_file or args.file
    if not file_path:
        parser.error("A video file must be provided either as positional argument or with --source")

    url = f"rtsp://localhost:8554/{args.cam}"
    print(f"Starting fake camera stream from {file_path} to {url}")
    
    cmd = [
        "ffmpeg",
        "-re",
        "-stream_loop", "-1",
        "-i", file_path,
        "-an",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-r", str(args.fps),
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        url
    ]
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("Stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
