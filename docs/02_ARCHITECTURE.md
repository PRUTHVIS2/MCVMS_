# 02_ARCHITECTURE.md

## 1. Three separate paths (never mix them)
1. **Live view:** camera -> MediaMTX -> browser (WebRTC, HLS fallback). No AI in this path. Boxes are drawn in the browser from WebSocket data. Never burn overlays into video.
2. **Analysis:** camera RTSP (a second, low-load connection) -> `Analyzer` per camera -> tracks -> attribute workers -> rule engine -> events.
3. **Recording:** camera RTSP -> FFmpeg `-c copy` segments (rolling) -> clips are cut from segments after the fact (`docs/07_STORAGE.md`).
Batch mode replaces path 2's source (and path 3's source) with recorded files.

## 2. Process model
One backend process (FastAPI + asyncio) plus threads, plus FFmpeg child processes managed by a supervisor. Simpler than process-per-camera, and models share the GPU. If the benchmark (step 20) shows the event loop or GIL is the bottleneck, propose a change; do not do it up front.
```
FrameSource(thread) -> latest-frame slot (drop old) -> Analyzer(thread, one per camera)
  Analyzer: detect+track (every frame) -> TrackStore -> RuleEvaluator (pure, each tick)
            -> AttributeJobs (bounded queues, never block the analyzer):
                 PlateWorker   (crop from full-res, detect plate, OCR)
                 ColourInline  (cheap, on analyzer thread)
                 PoseIdWorker  (torso crop + classifier, only for person tracks that need it)
                 EmbedWorker   (appearance embedding for vehicle sightings)
  FinalizerThread: track end -> SightingFinalizer (vote, match, link identity, review item, clip request)
EventService (asyncio) <- RuleEvaluator outputs -> DB, clips, alerts, WebSocket
Supervisor: FFmpeg recorders, health, retention, backup
```
Communication from threads to asyncio only via `loop.call_soon_threadsafe` or thread-safe queues drained by an async task.

## 3. Compute plan (12 GB GPU)
| Model | Used for | Runs | Notes |
|---|---|---|---|
| YOLO11s detect (`models.vehicle_detector`) | vehicles, persons | every analysed frame on cameras with `vehicles` | class map in config, custom classes (auto_rickshaw, tempo) can be added later |
| YOLO11s-pose (`models.person_pose`) | person boxes + keypoints | every analysed frame on cameras with `id_check` | replaces the detector for persons on those cameras |
| Plate detector (`models.plate_detector`) | plate box on a vehicle crop | only on qualifying vehicle tracks, rate-limited | weights supplied by the human |
| OCR (EasyOCR/PaddleOCR) | plate text | only on plate crops | CPU or GPU, configurable |
| ID classifier (YOLO11-cls, `models.id_classifier`) | torso crop -> id_visible / no_id_visible / unusable | only on person tracks inside or approaching a zone that has an armed `id_state` rule | weights trained by the human |
| Appearance embedder (`identity.embedder`) | vehicle embedding | once or twice per sighting | model chosen at step 14 by measurement |
Lazy rule: a model is loaded and run only if some camera/rule needs it. A worker whose weights are missing disables that feature, warns in the UI, and never crashes the app.

## 4. Data types (`app/core/types.py`, frozen dataclasses)
- `Detection(cls, conf, xyxy, keypoints|None)` in full-resolution pixel coordinates.
- `TrackedObject(track_id, cls, conf, xyxy, foot_point, ts_ms, keypoints|None)`.
- `TrackedFrame(camera_id, ts_ms, frame_size, objects)`.
- `AttrValue(value, conf, state: 'known'|'unknown', n_obs, updated_ms)`.
- `TrackAttributes(track_id, kind: 'vehicle'|'person', attrs: dict[str, AttrValue])`.
Coordinate rule: detection runs on a downscaled frame (`analysis.detect_max_side`); boxes are scaled back to full-res immediately. All geometry (zones, lines, crops) is in full-res pixels. Zones are stored normalised (0..1) and converted per stream size.

## 5. Modes
- `live`: wall-clock time (NTP synced), RTSP sources, FFmpeg recorders.
- `batch` (`python -m app.tools.process_video`): file sources, deterministic time from the file (`--start "2026-10-05T08:30:00+05:30"` or the filename pattern `YYYYMMDD_HHMMSS`), as fast as possible. Same code path for rules, attributes, sightings and clips (clips are cut from the file itself). This is how real recorded footage is evaluated.

## 6. Time
`core/clock.py` gives `Clock` (real) and `SimulatedClock` (tests). Events use the frame's source timestamp (`ts_ms`), not arrival time, so batch and replay behave identically.

## 7. Failure behaviour (each module implements its row)
| Failure | Behaviour |
|---|---|
| Camera unreachable / frozen (no new frame for `health.frozen_stream_after_seconds`) | reconnect with backoff, `camera_offline` alert (medium) once, `camera_online` when back, tracks closed cleanly |
| Detector weights missing | app starts, camera marked `degraded`, UI banner |
| Plate / OCR / pose / ID / embedder missing or crashing | that feature disabled, warning, sightings still saved with `needs_review` (vehicles) or `id_state=unknown` (persons) |
| Worker queue full | drop oldest job, increment counter shown on System page |
| FFmpeg recorder dies | supervisor restarts within 5 s, `recording_gap` logged, clips overlapping a gap marked `incomplete` |
| Clip cut fails | event/sighting still saved, clip `needs_repair`, retried every 5 min up to 5 times, then one alert |
| DB locked/corrupt | WAL mode, busy timeout, integrity check on start, rebuild from sidecar JSON (`docs/07_STORAGE.md`) |
| Disk fills | watermark policy in `config/storage_policy.yaml` |
| Rule references a deleted zone/camera | rule disabled, `system.warning` |

## 8. Repository layout
```
mcvms/
  AGENT_RULES.md PLAN.md PROGRESS.md IDEAS.md BLOCKED.md(when needed)
  docs/            spec, DECISIONS.md, results/
  config/          app.yaml storage_policy.yaml
  test_data/       clips + answer files (human supplied, read-only for the agent)
  data/            runtime (gitignored): db, clips, continuous, models, dataset, exports
  backend/
    pyproject.toml
    app/
      main.py config.py
      core/        clock.py types.py health.py log.py geometry.py
      db/          schema.sql migrations.py repo_*.py
      auth/        security.py deps.py roles.py
      sources/     rtsp.py filesource.py timesource.py
      vision/      detector.py tracker.py crops.py colour.py pose.py
      attributes/  vehicle_attrs.py id_state.py store.py      (pure where possible)
      plates/      detect.py ocr.py preprocess.py normalise.py voting.py worker.py
      matching/    weighted_edit.py tiers.py registry_repo.py
      identity/    vehicles.py sightings.py embed.py linking.py
      rules/       geometry.py conditions.py engine.py schedule.py escalation.py   (PURE)
      pipeline/    analyzer.py camera_runtime.py finalizer.py
      recorder/    ffmpeg_recorder.py clipper.py retention.py integrity.py
      services/    events.py alerts.py review.py notifier.py
      api/         routers per resource, ws.py
      tools/       process_video.py run_rules.py fake_camera.py annotate.py id_probe.py plate_probe.py bench.py rebuild_index.py export_training.py
    tests/
    scripts/       plate_baseline.py id_baseline.py train_id_classifier.py plot_bench.py
  frontend/        src/{pages,components,lib}
```

## 9. Technology (fixed)
Python 3.11, FastAPI, SQLite (WAL, FTS5 trigram), Ultralytics YOLO11 (+ ByteTrack), Ultralytics classification for the ID classifier, EasyOCR (PaddleOCR optional fallback), OpenCV, FFmpeg, MediaMTX, React + Vite + TypeScript + Tailwind. Pydantic for config and API models. `python-jose` or `pyjwt` + `passlib[argon2]` or bcrypt for auth. **Verify each package against the installed version before using its API.**

## 10. Latency stamps (used by `tools/bench`)
`t_frame_captured`, `t_detected`, `t_rule_fired`, `t_event_saved`, `t_alert_sent`, `t_clip_ready`. Report p50/p95/max of `t_rule_fired -> t_alert_sent` and `t_rule_fired -> t_clip_ready`. State that camera encode and network delay are excluded.

## 11. Configuration
All keys, defaults and rationale: `config/app.yaml` and `config/storage_policy.yaml`. The config loader must fail fast on unknown or invalid keys and print the offending path.
