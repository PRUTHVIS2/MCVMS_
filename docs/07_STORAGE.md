# 07_STORAGE.md (recording, clips, retention, integrity)

All numbers live in `config/storage_policy.yaml` (with WHY/FAILURE comments). This file explains the behaviour.

## 1. Three kinds of stored data
| Data | Where | Kept |
|---|---|---|
| Continuous segments (rolling source for cutting) | `data/continuous/<camera>/YYYYMMDD_HHMMSS.mkv` | `continuous.retention_hours` (default 12) |
| Clips: `event` (registered action fired) and `sighting` (10 s per vehicle sighting) | `data/clips/<yyyy>/<mm>/<dd>/<camera>/<id>.mp4` + `<id>.meta.json` + key frames | by retention class |
| Metadata: vehicles, sightings, events, plate reads, id_checks | SQLite `data/mcvms.db` | `retention.metadata_days` (365), review-pending never deleted |
Also short-lived: ID-card evidence crops (`retention.id_evidence_days`, 30), plate crops (kept with metadata), datasets under `dataset/` (never auto-deleted, gitignored).

## 2. Continuous recording (live mode)
One FFmpeg per camera: `-rtsp_transport tcp -i <url> -an -c copy -f segment -segment_time 10 -segment_format matroska -strftime 1 -reset_timestamps 1 ...`. No re-encode (almost no CPU/GPU), no audio (privacy), MKV so a crash or power cut does not corrupt the segment. Camera keyframe interval should be 1 to 2 s. A supervisor restarts a dead recorder within 5 s and logs a `recording_gap`; clips overlapping a gap are `incomplete`.

## 3. Cutting clips (`recorder/clipper.py`)
- **Event clip:** from `start - pre_roll_s` (15) until the event ends plus `hold_s`, capped at `max_clip_min` (per rule, default by severity). Long events keep their first `max_clip_min`; the key frames cover the rest.
- **Sighting clip:** exactly 10 s (docs/05 section 6).
- Method: find segments overlapping the window, concat, trim, re-encode H.264 (`h264_nvenc`, fallback `libx264`) for frame-accurate, browser-safe output, no audio. Write to a temp file then atomic rename. Compute SHA-256 and write the sidecar.
- Cut only after the covering segments exist (wait up to 15 s). A failed cut leaves the row `needs_repair` and retries every 5 min, 5 times, then one alert.
- Batch mode cuts from the source file itself.

## 4. Sidecar JSON (`<id>.meta.json`)
Everything needed to rebuild the DB row: ids, kind, camera, times, severity or sighting summary (category, colour, plate, status, vehicle tag), zones, hashes, key frame names. `python -m app.tools.rebuild_index` rebuilds `clips`, `events`, `sightings` and `vehicles` (by plate) from sidecars if the DB is lost.

## 5. Retention classes
Each clip gets `retention_class` and `expires_at` at creation (values in the YAML): event clips by severity (`event_low`, `event_medium`, `event_critical`), `sighting_resolved`, `sighting_verify`, `sighting_confirmed`, `sighting_unregistered`, `sighting_needs_review` (until resolved), `pinned` (keep). **Protected** clips (open event or pending review) are never deleted. The retention job runs hourly, deletes only paths inside configured data directories, and audits each deletion batch.

## 6. Disk watermarks
Warn at 80 percent (alert admin), clean at 90 percent (delete in `cleanup_order`), emergency at 95 percent (stop continuous recording, keep creating events and sightings, skip new clip video, alert loudly). Protected and pinned items are never auto-deleted. Estimate storage needs at step 20 and print them (`tools/bench --storage-estimate`): cameras x bitrate x hours plus expected clips per day x size.

## 7. Integrity, audit, backup
SHA-256 per clip, weekly verification, mismatch marks `corrupt` and alerts. Audit actions: view_clip, export_clip, delete_clip, pin_clip, correct_plate, confirm_plate, dismiss_alert, registry_change, zone/rule change, user change, merge/split vehicle, id feedback. Optional backup path (`paths.backup`, disabled by default) copies pinned and confirmed items with hash verification and retries.

## 8. Health
Frozen stream after `health.frozen_stream_after_seconds` (30) -> reconnect with backoff `[1,2,4,8,16,32,60]` s, one `camera_offline` alert. Disk write test on start. Time sync (NTP) required in live mode; warn if the clock cannot be verified.
