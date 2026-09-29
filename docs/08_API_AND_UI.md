# 08_API_AND_UI.md

REST under `/api/v1`, JSON, pydantic models, JWT bearer auth (+ httpOnly cookie for the video player). Errors: `{"error":{"code","message","details"}}`. Times are epoch ms. Pagination `?limit&cursor`. Every endpoint enforces role permissions server-side.

## 1. Permission matrix
| Capability | Owner | Admin | In-charge |
|---|---|---|---|
| Users, retention, data wipe | yes | no | no |
| Cameras, zones, registered actions, calendar exemptions | yes | yes | no |
| Registry (import, edit) | yes | yes | no |
| Owner names in registry / vehicle views | yes | yes | **hidden** |
| Review queue actions (confirm, correct, dismiss) | yes | yes | yes (no "register new vehicle") |
| Vehicles page, sightings, plates | yes | yes | yes (assigned cameras) |
| Merge / split vehicles | yes | yes | no |
| Live wall, events, clips | yes | yes | yes (assigned cameras); ID-card evidence only if `privacy.incharge_can_view_id_clips` |
| Acknowledge alert / event | yes | yes | yes |
| Dismiss alert, mark false alarm | yes | yes | no |
| System page, audit log | yes | yes | read-only system |

## 2. Endpoints (grouped)
- **Auth:** `POST /auth/login`, `POST /auth/logout`, `GET /me`.
- **Cameras:** `GET/POST /cameras`, `PATCH/DELETE /cameras/{id}` (features `vehicles`, `id_check`), `POST /cameras/{id}/test`, `GET /cameras/{id}/snapshot`, `GET /cameras/{id}/stream-info`. RTSP URLs are never returned.
- **Zones:** `GET/POST /cameras/{id}/zones`, `PATCH/DELETE /zones/{id}`. Body has `kind` (`normal|special`), `shape`, `points`, `direction`, `is_read_area`. Validation of geometry. Changing `kind` special->normal with actions returns 409.
- **Registered actions:** `GET /zones/{id}/actions`, `POST /zones/{id}/actions` (**422 `zone_not_special` if the zone is normal**), `PATCH/DELETE /actions/{id}`, `GET /rule-templates` (templates, attribute catalogue, presets, applicability), `POST /actions/{id}/dry-run` (`clip_id` or uploaded test clip).
- **Calendar exemptions:** `GET/POST/DELETE /calendar`.
- **Events:** `GET /events` (filters: camera, zone, action, severity, status, date range, vehicle), `GET /events/{id}`, `POST /events/{id}/ack`, `POST /events/{id}/false-alarm` (reason; for ID events also saves the evidence to the feedback set), `GET /events/{id}/clip` (range requests).
- **Alerts:** `GET /alerts`, `POST /alerts/{id}/ack`, `POST /alerts/{id}/dismiss` (reason required).
- **Vehicles:** `GET /vehicles` (search by plate partial via FTS, category, colour, camera, zone, date range, registry status), `GET /vehicles/{id}` (details + timeline of sightings), `PATCH /vehicles/{id}` (label, notes, pin), `POST /vehicles/{id}/merge`, `POST /vehicles/{id}/split`.
- **Sightings:** `GET /sightings`, `GET /sightings/{id}`, `GET /sightings/{id}/clip`, `POST /sightings/{id}/pin`.
- **Review queue:** `GET /review` (sorted by due, priority), `GET /review/{id}`, `POST /review/{id}/confirm|correct|register|visitor|link|dismiss|skip`.
- **Registry:** `GET/POST /registry`, `PATCH/DELETE /registry/{id}`, `POST /registry/import?dry_run=true|false` (CSV columns: plate, kind, category, colour, owner_label, valid_from, valid_until, note; dry run returns row-level errors and duplicate/near-duplicate warnings), `POST /registry/rematch`.
- **ID checks (admin):** `GET /id-checks` (state, camera, date), `GET /id-checks/{id}` (evidence).
- **System:** `GET /system/health` (camera status, FPS, queue drops, disk, worker status, GPU, spot-check wrong-accepted rate), `GET /system/config-summary`, `GET /audit`.
- **WebSocket** `/ws` (token in query or first message): `alert.created`, `alert.updated`, `event.created|updated|ended`, `sighting.created`, `review.created`, `camera.status`, `tracks` (live boxes: id, class, box, attributes, in-zone flags) at up to 10 Hz per subscribed camera. `subscribe {camera_ids}` / `unsubscribe`.

## 3. Screens (React + Vite + TypeScript strict + Tailwind, dark theme)
1. **Login.**
2. **Live wall:** grid of cameras (WebRTC via MediaMTX, HLS fallback) with a canvas overlay: boxes, track id, attribute chips (truck, white, KA05..., "no ID?"), zone outlines (special zones drawn dashed amber, normal zones dotted grey), status dot. Click opens a large view. Alert bell with severity colours and sound option.
3. **Events:** filterable list, detail drawer with clip player (pre-roll marker), key frames, subject attributes, vehicle tag link, ack / false alarm buttons.
4. **Vehicles:** searchable table (plate, category, colour, last seen, sightings count, registry kind); detail page with **timeline of sightings** across cameras and days, each with its 10 s clip; merge/split; pin.
5. **Review queue:** big evidence panel (best frame, plate crop, top-3 candidates, appearance candidates, clip); keyboard shortcuts 1/2/3 confirm, C correct, R register, D dismiss, S skip; progress "12 left, 3 overdue".
6. **Registry:** table, add/edit, CSV import with dry-run report.
7. **Setup (wizard, section 4) and Cameras/Zones/Rules manager.**
8. **Alerts** list (levels, ack, dismiss).
9. **ID checks (admin):** list of id_checks with evidence crops, feedback buttons (confirm / false alarm).
10. **System:** camera status, FPS, queue drops, disk, worker status, measured plate wrong-accepted rate (with interval), latency stats, "About accuracy" (limitations list from docs/01 s6).
11. **Users and audit** (owner).

## 4. Setup wizard (`Setup` page, step 10 of PLAN)
For a selected camera:
1. **Camera features:** switches "vehicle detection" and "ID-card check". Explains what each needs (camera placement tips; link to probe results).
2. **Draw zones on the live snapshot:** polygon tool (click points, double click to close), line tool with direction arrow and flip button, drag handles to edit, undo, names, colour. For each zone choose **Kind: Normal (just record who passes) or Special (can have registered actions)**; for normal polygons an optional "use as plate read area" toggle.
3. **Registered actions (only shown for special zones):** rule builder with presets:
   - *Heavy vehicle in zone* (vehicle, category picker, schedule),
   - *Unregistered vehicle in zone* (vehicle, `registry_status=unregistered`),
   - *Vehicle stays too long* (dwell),
   - *Vehicle count above N* (count_threshold),
   - *Vehicle crosses line* (line_crossing),
   - *Person without visible ID card* (person, `id_state=not_wearing`).
   Fields: what to look for (subject + conditions in plain words), armed schedule (days + from/to), active dates (from/until), how long before alert (min seconds), severity, escalation rows ("if 5 in 10 minutes then medium"), cooldown, alert expiry, exemptions (pick calendar entries), pre-roll/hold. A sentence summary is shown live ("Raise a CRITICAL alert if a truck or bus stays in 'Loading bay' for 2 s, Mon-Sat 09:00-17:00").
4. **Dry run:** pick a stored clip or upload one; shows the timeline of what would fire with markers, without creating alerts.
5. **Save and arm.** Rules can be paused/edited later; edits are audited.
Selecting a normal zone hides the "add registered action" control and explains why.

## 5. Alert wording (one line, no jargon)
- Rule event: `{severity icon} {rule name} · {camera} · {zone} · {HH:MM}` plus `(escalated)` when applicable.
- Vehicle rule: adds `{category} {colour} {plate or "plate unknown"}`.
- ID rule: `Person without visible ID · {camera} · {zone} · {HH:MM}` (never "student").
- System: `camera_offline`, `disk_low`, `recording_gap`, `worker_disabled`, `review_digest` etc.
Delivery: dashboard bell + list + WebSocket. `Notifier` interface has disabled stubs for email/Telegram.
