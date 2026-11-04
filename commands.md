# MCVMS Execution Commands

This document contains commands to start the simulated camera streams (`cam01`, `cam02`, `cam03`, and `cam04`), the backend server, and the frontend server.

---

## 0. Prerequisite: Start MediaMTX (RTSP Server)

The camera streams publish via RTSP to MediaMTX on port 8554. MediaMTX must be running before starting the camera streams.

In a dedicated terminal:
```powershell
C:\mediamtx\mediamtx.exe
```
*(Or run `mediamtx` if it is configured in your system PATH)*

---

## 1. Start `cam01` (Looping `car_exit.mp4`)

Publishes `test_data/events/car_exit.mp4` in an infinite loop to `rtsp://localhost:8554/cam01`.

### Option A: From Repository Root
```powershell
backend\.venv\Scripts\python backend\app\tools\fake_camera.py test_data/events/car_exit.mp4 --cam cam01
```

### Option B: From `backend` Directory
```powershell
cd backend
.venv\Scripts\python -m app.tools.fake_camera ../test_data/events/car_exit.mp4 --cam cam01
```

### Option C: Looping `exit_gate_17.mp4`
```powershell
backend\.venv\Scripts\python backend\app\tools\fake_camera.py test_videos/exit_gate_17.mp4 --cam cam01
```
*(Or from `backend` directory: `cd backend; .venv\Scripts\python -m app.tools.fake_camera ../test_videos/exit_gate_17.mp4 --cam cam01`)*

### Alternative: Raw FFmpeg Command
```powershell
ffmpeg -re -stream_loop -1 -i test_data/events/car_exit.mp4 -an -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -b:v 4M -maxrate 4M -bufsize 8M -g 30 -r 30 -f rtsp -rtsp_transport tcp rtsp://localhost:8554/cam01
```

---

## 2. Start `cam02` (Looping `car_dwell.mp4`)

Publishes `test_data/events/car_dwell.mp4` in an infinite loop to `rtsp://localhost:8554/cam02`.

### Option A: From Repository Root
```powershell
backend\.venv\Scripts\python backend\app\tools\fake_camera.py test_data/events/car_dwell.mp4 --cam cam02
```

### Option B: From `backend` Directory
```powershell
cd backend
.venv\Scripts\python -m app.tools.fake_camera ../test_data/events/car_dwell.mp4 --cam cam02
```

### Alternative: Raw FFmpeg Command
```powershell
ffmpeg -re -stream_loop -1 -i test_data/events/car_dwell.mp4 -an -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -b:v 4M -maxrate 4M -bufsize 8M -g 30 -r 30 -f rtsp -rtsp_transport tcp rtsp://localhost:8554/cam02
```

---

## 3. Start `cam03` (Looping `entry_17.mp4`)

Publishes `test_videos/entry_17.mp4` in an infinite loop to `rtsp://localhost:8554/cam03`.

### Option A: From Repository Root
```powershell
backend\.venv\Scripts\python backend\app\tools\fake_camera.py test_videos/entry_17.mp4 --cam cam03
```

### Option B: From `backend` Directory
```powershell
cd backend
.venv\Scripts\python -m app.tools.fake_camera ../test_videos/entry_17.mp4 --cam cam03
```

### Alternative: Raw FFmpeg Command
```powershell
ffmpeg -re -stream_loop -1 -i test_videos/entry_17.mp4 -an -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -b:v 4M -maxrate 4M -bufsize 8M -g 30 -r 30 -f rtsp -rtsp_transport tcp rtsp://localhost:8554/cam03
```

---

## 4. Start `cam04` (Looping `material_gate_18.mp4`)

Publishes `test_videos/material_gate_18.mp4` in an infinite loop to `rtsp://localhost:8554/cam04`.

### Option A: From Repository Root
```powershell
backend\.venv\Scripts\python backend\app\tools\fake_camera.py test_videos/material_gate_18.mp4 --cam cam04
```

### Option B: From `backend` Directory
```powershell
cd backend
.venv\Scripts\python -m app.tools.fake_camera ../test_videos/material_gate_18.mp4 --cam cam04
```

### Alternative: Raw FFmpeg Command
```powershell
ffmpeg -re -stream_loop -1 -i test_videos/material_gate_18.mp4 -an -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -b:v 4M -maxrate 4M -bufsize 8M -g 30 -r 30 -f rtsp -rtsp_transport tcp rtsp://localhost:8554/cam04
```

---

## 5. Start Backend Server (FastAPI / Uvicorn)

Runs the FastAPI backend API and background camera monitor pipeline on port 8000.

### Option A: From `backend` Directory (Standard)
```powershell
cd backend
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Option B: From Repository Root
```powershell
backend\.venv\Scripts\uvicorn --app-dir backend app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **API Base URL:** `http://localhost:8000`
- **Swagger Docs:** `http://localhost:8000/docs`
- **Health Check:** `http://localhost:8000/health`

---

## 6. Start Frontend Server (Vite / React)

Runs the frontend development server on port 5173.

### Option A: From `frontend` Directory (Standard)
```powershell
cd frontend
npm run dev
```

### Option B: From Repository Root
```powershell
npm --prefix frontend run dev
```

- **Frontend UI:** `http://localhost:5173`
- **Default Credentials:**
  - Owner: `admin` / `adminpass`
  - In-charge: `incharge1` / `inchargepass`

---

## Quick Multi-Terminal Overview

| Terminal | Purpose | Command (from repo root) |
|---|---|---|
| **Terminal 1** | MediaMTX | `C:\mediamtx\mediamtx.exe` |
| **Terminal 2** | `cam01` Stream | `backend\.venv\Scripts\python backend\app\tools\fake_camera.py test_data/events/car_exit.mp4 --cam cam01` |
| **Terminal 3** | `cam02` Stream | `backend\.venv\Scripts\python backend\app\tools\fake_camera.py test_data/events/car_dwell.mp4 --cam cam02` |
| **Terminal 4** | `cam03` Stream | `backend\.venv\Scripts\python backend\app\tools\fake_camera.py test_videos/entry_17.mp4 --cam cam03` |
| **Terminal 5** | `cam04` Stream | `backend\.venv\Scripts\python backend\app\tools\fake_camera.py test_videos/material_gate_18.mp4 --cam cam04` |
| **Terminal 6** | Backend API | `cd backend; .venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` |
| **Terminal 7** | Frontend Web | `cd frontend; npm run dev` |

