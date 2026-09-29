import sqlite3
import subprocess
import sys


def check_python() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

def check_torch_cuda() -> tuple[str, bool]:
    try:
        import torch
        return torch.__version__, torch.cuda.is_available()
    except ImportError:
        return "Not installed", False

def check_ultralytics() -> str:
    try:
        import ultralytics
        return ultralytics.__version__
    except ImportError:
        return "Not installed"

def check_opencv() -> str:
    try:
        import cv2
        return cv2.__version__
    except ImportError:
        return "Not installed"

def check_ffmpeg() -> str:
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout.splitlines()[0].split("version ")[1].split(" ")[0]
        return "Error running ffmpeg"
    except FileNotFoundError:
        return "Not found"

def check_sqlite() -> tuple[str, bool]:
    version = sqlite3.sqlite_version
    fts5_trigram = False
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE test_fts USING fts5(text, tokenize='trigram')")
        fts5_trigram = True
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    return version, fts5_trigram

def check_ocr() -> str:
    engines = []
    try:
        import easyocr
        engines.append(f"EasyOCR {easyocr.__version__}")
    except ImportError:
        pass
    # PaddleOCR is optional, omit here for brevity or just try
    return ", ".join(engines) if engines else "None"

def check_node() -> str:
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        return "Error running node"
    except FileNotFoundError:
        return "Not found"

def main():
    print("Environment Check:")
    py_ver = check_python()
    print(f"Python: {py_ver}")
    
    torch_ver, cuda = check_torch_cuda()
    print(f"PyTorch: {torch_ver}, CUDA available: {cuda}")
    
    yolo_ver = check_ultralytics()
    print(f"Ultralytics: {yolo_ver}")
    
    cv2_ver = check_opencv()
    print(f"OpenCV: {cv2_ver}")
    
    ffmpeg_ver = check_ffmpeg()
    print(f"FFmpeg: {ffmpeg_ver}")
    
    sqlite_ver, fts5 = check_sqlite()
    print(f"SQLite: {sqlite_ver}, FTS5 Trigram: {fts5}")
    
    ocr = check_ocr()
    print(f"OCR: {ocr}")
    
    node = check_node()
    print(f"Node: {node}")

if __name__ == "__main__":
    main()
