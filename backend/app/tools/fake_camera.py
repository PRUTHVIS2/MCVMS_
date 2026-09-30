import argparse
import subprocess
import time
import sys

def main():
    parser = argparse.ArgumentParser(description="Fake Camera RTSP stream loop")
    parser.add_argument("file", help="Video file to loop")
    parser.add_argument("--cam", default="cam01", help="Camera name in RTSP path (e.g. cam01 -> rtsp://localhost:8554/cam01)")
    parser.add_argument("--fps", type=int, default=25, help="Target FPS")
    args = parser.parse_args()
    
    url = f"rtsp://localhost:8554/{args.cam}"
    print(f"Starting fake camera stream from {args.file} to {url}")
    
    cmd = [
        "ffmpeg",
        "-re",
        "-stream_loop", "-1",
        "-i", args.file,
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
