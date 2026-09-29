# PLAN.md (the order of work; one step at a time, human-gated)

Rules of the gate are in `AGENT_RULES.md` section 2. Each step lists: **Depends on**, **Tasks**, **Tests** (all earlier tests must also pass), **Human checkpoint**, **Done when**. Spec references point into `docs/`.

Phases: **A** Foundation (0-10) - **B** Vehicles (11-16) - **C** ID card (17-19) - **D** Finish (20-21).

---
## PHASE A: FOUNDATION (zones, rules, clips, alerts)

### Step 0: Skeleton and environment check
**Depends on:** nothing. **Docs:** 02.
**Tasks:** create the repo layout (docs/02 s8), `pyproject.toml`, `config.py` (pydantic-settings loading `config/app.yaml` and `storage_policy.yaml`, fail fast on unknown keys), logging setup, `core/clock.py`, FastAPI app with `GET /health`, `frontend/` Vite+React+TS+Tailwind scaffold with a placeholder page, `ruff`/`pytest`/`vitest` configured. `tools/env_check.py` prints and returns versions: Python, torch + CUDA availability, ultralytics, opencv, ffmpeg/ffprobe, SQLite version and **FTS5 trigram support**, easyocr/paddleocr importable, Node. Fill the Environment table in PROGRESS.md.
**Tests:** config loads and rejects an unknown key; `/health` returns ok; clock tests; env_check runs on a machine without GPU without crashing.
**Human checkpoint:** run `python -m app.tools.env_check` and `uvicorn app.main:app`, open `/health`, run `npm run dev`. Confirm CUDA shows True.
**Done when:** everything above works and PROGRESS.md environment table is filled.

### Step 1: Database, auth, roles, audit
**Depends on:** 0. **Docs:** 03, 08 (auth, permissions).
**Tasks:** migrations runner + full schema from docs/03 including **all triggers**; repositories; owner bootstrap from `.env`; login (argon2/bcrypt, JWT, rate limit), `GET /me`; role dependencies; audit writer; camera-scoped access for In-charge; Fernet helper for RTSP URLs; user management endpoints (owner).
**Tests:** schema creates from scratch; triggers: inserting a registered action on a normal zone aborts, downgrading a zone with actions aborts; login success/failure/rate limit; permission matrix skeleton (grows every step); password never logged; audit rows written.
**Human checkpoint:** log in via the API docs page as owner, create an admin and an in-charge user, confirm the in-charge cannot call an admin endpoint.
**Done when:** tests pass and the human confirms.

### Step 2: Frame sources, time sources, cameras, health
**Depends on:** 1. **Docs:** 02 s1-3,5-7, 07 s8.
**Tasks:** `sources/rtsp.py` (OpenCV/FFmpeg reader thread, latest-frame slot, reconnect backoff, frozen-stream detection), `sources/filesource.py` (paced or fast), `sources/timesource.py` (wall clock, `--start`, filename pattern `YYYYMMDD_HHMMSS`), camera CRUD API (encrypted URLs, features), snapshot endpoint, `POST /cameras/{id}/test`, `core/health.py`, `tools/fake_camera.py` (loop a file to `rtsp://localhost:8554/camN` with ffmpeg, no audio), `tools/make_synthetic_clip.py` (moving coloured boxes along known paths).
**Tests:** file source yields frames with correct timestamps; frozen stream detected using a scripted source; reconnect backoff sequence; RTSP URL never in any API response; (integration) fake_camera + MediaMTX -> reader gets frames.
**Human checkpoint:** start MediaMTX, `fake_camera` for cam01, add the camera, see snapshot, kill the stream and watch status flip to offline then back.
**Done when:** the camera lifecycle works with real and simulated sources.

### Step 3: Detection and tracking
**Depends on:** 2. **Docs:** 02 s3-4, 05 s1 (start), 06 s3 (step 1).
**Tasks:** `vision/detector.py` (Ultralytics YOLO11, class map, downscale + map back to full-res, device handling with warning, verify API of the installed version), tracker (ByteTrack via Ultralytics, one instance per camera), `core/types.py`, `vision/crops.py` (`crop_full_res`), `pipeline/analyzer.py` (reader -> detector -> `TrackedFrame` -> subscribers), `ScriptedDetector` for tests, `tools/annotate.py` (writes an annotated MP4 for the human, never used in the live path), pose model wrapper (`vision/pose.py`, loads lazily), WebSocket `tracks` stream skeleton.
**Tests:** downscale/upscale coordinate round-trip; `crop_full_res` pixel-accuracy on a known pattern; scripted detector drives the analyzer deterministically; class map filters non-vehicle classes; analyzer never blocks when the consumer is slow (drop-oldest); (gpu) real model detects a person and a vehicle in a sample frame.
**Human checkpoint:** run `annotate` on a clip; boxes and ids look right; FPS printed.
**Done when:** stable tracks on real clips.

### Step 4: Zones, attributes and rule engine (pure)
**Depends on:** 3. **Docs:** 04 (all), 03 (registered_actions).
**Tasks:** `core/geometry.py`, `rules/` package exactly per docs/04: geometry, conditions, engine, schedule, escalation, compile from validated JSON; `attributes/store.py` (TrackAttributes with known/unknown); pydantic models for zone and rule spec; `tools/run_rules.py` (batch a clip + answer JSON, PASS/FAIL diff, also runs on synthetic clips); answer-file loader per `test_data/events/README.md`.
**Tests:** every test in docs/04 s8, plus determinism and grep test. Ship generated synthetic clips + answers in `tests/synthetic/` (heavy-truck-in-zone, flicker, line crossing, dwell, count, schedule boundary) and run them through `run_rules`.
**Human checkpoint:** run `run_rules` on the synthetic clips and on `test_data/events/*` clips you have recorded; read the PASS/FAIL table; report any mismatch to the agent.
**Done when:** zero mismatches on synthetic and the human's supplied clips (or human-approved list of mismatches).

### Step 5: Recording and clips
**Depends on:** 4. **Docs:** 07 s2-4, 05 s6, 02 s7.
**Tasks:** `recorder/ffmpeg_recorder.py` (per camera, supervised), `recorder/clipper.py` (segment lookup, concat, trim, re-encode, atomic write, SHA-256, sidecar, key frames) for **both kinds** (`event` with variable length, `sighting` with exactly 10 s), retry/repair loop, `tools/rebuild_index.py`, batch-mode clip cutting from a source file.
**Tests:** clip window maths (pre-roll, hold, cap, 10 s window clamp); cut from generated segments gives the right duration (ffprobe) within one frame; atomic write leaves no partial file on crash; sidecar round-trip and rebuild_index restores rows; cut before segments exist waits then succeeds; recording gap marks `incomplete`; (integration) live recorder produces segments.
**Human checkpoint:** run the recorder for 2 minutes, request a 10 s clip and a 25 s clip by CLI, play both in a browser.
**Done when:** clips play in the browser and durations are correct.

### Step 6: Events and alerts
**Depends on:** 5. **Docs:** 04 s5-6, 05 s8, 08 s5, 03 (events, alerts).
**Tasks:** `pipeline/camera_runtime.py` (wires source, analyzer, engine, attributes, event service), `services/events.py` (Decision -> event rows, clip request, key frames, `event.updated` when attributes complete), `services/alerts.py` (one line messages, severity, **cooldown, TTL expiry, escalation via `escalation.pick_severity`**, no flooding: one open alert per (kind,target)), WebSocket push, acknowledge/false-alarm/dismiss with reasons, `Notifier` interface with disabled email/Telegram stubs, `camera_offline`/`disk_low` system alerts, exemption lookup (`calendar_exemptions`), rule loading and hot reload when rules change.
**Tests:** end-to-end synthetic: scripted heavy-truck track -> event -> alert -> clip request; escalation raises severity at 5 events in 10 min; cooldown suppresses repeat; TTL expiry; dismiss requires reason and role; exemption date suppresses; dry-run events never alert; permissions matrix updated.
**Human checkpoint:** with a real clip of a truck/bus through a zone (via `fake_camera`), watch an alert appear in the API docs WebSocket tester and the clip play.
**Done when:** real footage produces the expected event and clip within the latency goal (measure, do not claim).

### Step 7: Camera, zone and rule management API
**Depends on:** 6. **Docs:** 04 s1,5, 08 s2.
**Tasks:** zones CRUD with geometry validation and `kind`; **`POST /zones/{id}/actions` returns 422 `zone_not_special` for normal zones** (plus DB trigger); actions CRUD with pydantic validation of the spec (template/shape applicability, attribute catalogue, ops, schedule, dates), `GET /rule-templates` (templates, catalogue, presets), calendar exemptions CRUD, dry-run endpoint, audit for every change, hot reload into running pipelines.
**Tests:** every validation rule with a good and a bad payload; normal-zone gating at API level; changing zone kind with actions -> 409; unknown attribute or op -> 422; permission matrix updated; audit rows.
**Human checkpoint:** using the API docs page: create a normal zone (try adding an action, expect 422), a special zone, and a heavy-vehicle rule; see it live in a running camera.
**Done when:** rules can be managed entirely through the API.

### Step 8: Frontend: shell and live wall
**Depends on:** 7. **Docs:** 08 s3.1-2.
**Tasks:** app shell (login, role-aware nav), API client, WebSocket client with reconnect, live wall (WebRTC via MediaMTX with HLS fallback), overlay canvas from `tracks` messages (boxes, id, attribute chips, zone outlines: special dashed amber, normal dotted grey), alert bell with severity colours, camera status.
**Tests:** vitest for geometry/overlay maths and store; Playwright smoke (login, wall renders with a mocked backend).
**Human checkpoint:** open the wall with two fake cameras; overlay matches video; unplug a camera and see status change.
**Done when:** the wall is usable on a laptop screen.

### Step 9: Frontend: events, playback, system
**Depends on:** 8. **Docs:** 08 s3.3, 3.8, 3.10.
**Tasks:** events list + detail drawer (clip player with pre-roll marker, key frames, attributes, ack, false alarm), alerts page, system page (camera status, FPS, queue drops, disk), users and audit page (owner), "About accuracy" page from docs/01 s6.
**Tests:** vitest components; Playwright: open an event, play clip, acknowledge.
**Human checkpoint:** trigger three events; filter, play, acknowledge, mark one false alarm.
**Done when:** the event workflow is complete in the UI.

### Step 10: Frontend: setup wizard (MILESTONE A)
**Depends on:** 9. **Docs:** 08 s4, 04 s5.
**Tasks:** wizard exactly per docs/08 s4: feature switches, polygon and line drawing on the snapshot (undo, drag handles, direction arrow + flip), **zone kind selector (normal/special)**, rule builder shown only for special zones (presets, plain-language conditions, schedule, active dates, min seconds, severity, escalation rows, cooldown, alert expiry, exemptions), live sentence summary, dry run on a stored clip with a timeline, save and arm; zones/rules manager page; calendar exemptions editor.
**Tests:** vitest for the sentence generator and geometry helpers; Playwright: draw a normal zone (no rule option), draw a special zone, create the heavy-vehicle rule, run a dry run, arm it.
**Human checkpoint (Milestone A demo):** in the browser, draw a special zone, register "heavy vehicle in this zone, Mon-Sat 09:00-17:00, critical", play a clip with a truck: critical alert + clip with pre-roll. Show that a normal zone cannot take rules.
**Done when:** the full admin flow works without touching the API.

---
## PHASE B: VEHICLES

### Step 11: Plate baseline harness (DECISION GATE 1)
**Depends on:** 10 (or 4 for tools only). **Docs:** 05 s3, 09 s4.2, s5.
**Human supplies first:** at least 100 labelled passes (`test_data/vehicles/passes_ground_truth.csv`), `registry_test.csv`, and plate detector weights at `data/models/plate.pt` (agent may suggest where to find permissively licensed weights and how to train one; verify licences; agent never downloads without telling the human).
**Tasks:** `plates/` pure parts (`normalise`, `voting`, formats), `plates/detect.py`, `plates/ocr.py` (engine interface), `plates/preprocess.py`, `matching/` (weighted edit distance, tiers), `tools/plate_probe.py`, `scripts/plate_baseline.py` (runs the batch pipeline, produces every table in docs/09 s4.2 with breakdowns), unit tests with synthetic strings. **Do not tune thresholds; only measure.**
**Tests:** normalise/repair vectors (KA05AB1234 vs KA05A81234 style confusions, Bharat series), voting vectors (majority, length pick, single read rule, partial pattern), weighted edit distance and tiers vectors covering every table row, probe/baseline run on a tiny synthetic set.
**Human checkpoint:** read `docs/results/plate_baseline_<date>/`. **Decide together** what to do (docs/09 s5 Gate 1). Record the decision.
**Done when:** the baseline report exists and the decision is written to PROGRESS.md and `docs/DECISIONS.md`.

### Step 12: Vehicle attributes and plate pipeline (live)
**Depends on:** 11. **Docs:** 05 s1-3, 02 s2-3.
**Tasks:** `vehicle_attrs.py` (category vote, heavy), `vision/colour.py`, `PlateWorker` with bounded queue, read-area logic from normal zones, provisional attribute push (1 Hz) into the attribute store, decisions from Step 11 applied (preprocess chain, thresholds only if evidence exists), plate reads stored (crops), zones-visited recording, graceful degradation when weights or OCR are missing.
**Tests:** category vote and heavy derivation; colour on synthetic swatches incl. night -> unknown; worker drops oldest when full; missing weights disables plate reading without crash; plates never logged above DEBUG; zones-visited on scripted tracks; (gpu, integration) real clip produces reads.
**Human checkpoint:** run a vehicle clip live: live wall shows chips "white car KA05..." updating; unreadable ones show "plate ?".
**Done when:** attributes and provisional plates appear live and in rules (`heavy`, `category`, `colour`).

### Step 13: Registry and matching
**Depends on:** 12. **Docs:** 05 s4, 08 registry, 03 registry_entries.
**Tasks:** registry CRUD, CSV import with dry run (row errors, duplicates and near-duplicate plate warnings, date validation), `registry_repo`, active/valid-date filtering, `POST /registry/rematch`, wiring of matcher + tiers into the finalizer inputs, spot-check sampling logic, owner-name hiding for In-charge on every response model.
**Tests:** import dry run vs real import; duplicates; every tier row end-to-end; rematch touches only allowed statuses and dates; `test_names_hidden_for_incharge`; permissions updated.
**Human checkpoint:** import a small registry CSV, see the dry-run report, import it, look up one entry.
**Done when:** registry works and the matcher returns tiers on the baseline clips consistent with Step 11 numbers.

### Step 14: Vehicle identity, sightings, 10 s clips, review queue
**Depends on:** 13, 5. **Docs:** 05 s1,5,6,7, 03 (vehicles, sightings, review_items), 07.
**Tasks:** `SightingFinalizer` (vote, match, status, link, review item, sidecar, clip request), `identity/vehicles.py` (get_or_create by plate, fuzzy ghost prevention, merge/split with 30-day undo), duplicate suppression and clip min-gap, **10 s sighting clips**, review service with all admin actions, training samples + `tools/export_training`, alerts (`unresolved_plate`, `plate_mismatch`, digests), appearance embedding: embedder interface, `EmbedWorker`, candidate search, **embedder comparison gate** on `cross_camera_pairs.csv` (`scripts/embedder_compare.py`, report to `docs/results/`), disable appearance candidates if no embedder is useful, FTS partial plate search, `rebuild_index` handling vehicles/sightings.
**Tests:** finalizer idempotence; same plate on two cameras and two dates -> one vehicle; near-duplicate plate does not create a ghost; different vehicles never merged automatically; merge/split/undo; every review action; clip is exactly 10 s and duplicate-suppressed correctly; appearance candidates never auto-link; review deadlines; FTS finds `05AB` in `KA05AB1234`; permissions updated.
**Human checkpoint:** run two clips (two cameras) with the same vehicle; open the vehicles list via API: one tag, two sightings, two 10 s clips; resolve a review item.
**Done when:** persistent identity works across cameras and simulated days (batch mode with `--start` on different dates).

### Step 15: Vehicle-aware rules
**Depends on:** 14, 12. **Docs:** 04 s2 (attributes), s2 late binding.
**Tasks:** feed `plate`, `registry_status`, `registry_kind`, `vehicle_id`, `colour`, `body_type` from provisional and final identity into the attribute store, late-binding `event.updated` to complete `subject_json`, presets "unregistered vehicle in zone", "vehicle stays too long", "vehicle count above N", "vehicle crosses line"; make `run_rules` evaluate vehicle attributes using recorded clips.
**Tests:** unknown never matches for plate-dependent rules; rule fires when the plate resolves mid-track; event snapshot updated with the plate; cooldown per `vehicle_id`; all four presets on synthetic tracks; regression of all earlier rule tests.
**Human checkpoint:** register "unregistered vehicle in this zone after 18:00"; play a clip with a registered and an unregistered vehicle: only the second alerts.
**Done when:** vehicle rules behave correctly on real clips.

### Step 16: Frontend: vehicles, review, registry (MILESTONE B)
**Depends on:** 15. **Docs:** 08 s3.4-3.6.
**Tasks:** Vehicles table + search, vehicle detail with sighting timeline and 10 s clips, merge/split, review queue with evidence and keyboard shortcuts, registry table + CSV import with dry-run report, wizard presets for vehicle rules wired to the API.
**Tests:** vitest; Playwright: search a partial plate, open a vehicle, play a sighting clip, resolve a review item, import a registry CSV.
**Human checkpoint (Milestone B demo):** vehicles on two cameras -> one tag with timeline; unreadable plate -> review queue -> corrected; unregistered-vehicle rule fires.
**Done when:** Phase B demo works end to end.

---
## PHASE C: ID CARD

### Step 17: ID-card baseline harness (DECISION GATE 2)
**Depends on:** 10. **Docs:** 06 (all), 09 s4.4, s5.
**Human supplies first:** entrance footage of consenting people (wearing cards, not wearing, hidden/flipped, bag straps, different distances and lighting), `id_ground_truth.csv`, and sorted torso crops in `dataset/id/...` (or the agent's `extract_torso_crops` output to sort).
**Tasks:** `tools/id_probe.py`, `tools/extract_torso_crops.py`, `scripts/split_dataset.py` (clip-level splits, refuses frame-level leakage), `scripts/train_id_classifier.py` (verify the installed ultralytics classification API), `attributes/id_state.py` **pure `resolve`** with all rules from docs/06 s3.6, `scripts/id_baseline.py` (confusion matrices, false-accusation rate, unknown rate, breakdowns).
**Tests:** `resolve` vectors: enough good frames of `id_visible` -> wearing (sticky); 8 good frames no ID over 1 s -> not_wearing; 7 frames -> unknown; brief no-ID then clear card -> wearing; all frames low quality -> unknown with reason; back-turned -> unknown; determinism; torso crop geometry on synthetic keypoints; quality gate each condition; split script rejects leakage.
**Human checkpoint:** read `id_probe` (can this camera see torsos?), the training metrics, and `docs/results/id_baseline_<date>/`. **Decide together** (docs/09 s5 Gate 2). Record it.
**Done when:** baseline report exists and the decision is recorded.

### Step 18: ID state resolver, live integration, exemptions
**Depends on:** 17, 12 (attribute store), 6. **Docs:** 06 s2-4,7, 04 s5.
**Tasks:** `PoseIdWorker` (lazy: only tracks near a zone with an armed `id_state` rule; bounded queue; drop-oldest counter), wiring into the attribute store (`id_state` written on change), `id_checks` rows + evidence crops/snapshot with `id_evidence_days` retention, auto-retraction of `not_wearing` alerts when later evidence shows `wearing`, `person_no_id` preset (subject person, `min_box_px`, presence, severity, escalation), calendar exemptions and schedule applied to these rules, false-alarm feedback -> `dataset/id_feedback/`, optional lanyard allowlist (OFF by default; implement behind the flag only if the human requests it after Gate 2), missing-weights degradation (all `unknown`, banner).
**Tests:** `unknown` never fires; scripted track with 8 good no-ID frames fires once; later wearing evidence retracts; queue-full behaviour; lazy-run test (worker idle when no such rule); exemption date suppresses; escalation at 5 in 10 min; feedback copies crops; permissions (`incharge_can_view_id_clips` false hides evidence); regression.
**Human checkpoint:** play the entrance clip: people without a visible ID get low alerts, five within ten minutes escalate, wearers and unclear views produce nothing; look at the `id_checks` evidence.
**Done when:** the live behaviour matches the Gate 2 report within the human's tolerance.

### Step 19: Frontend: ID-card rule, evidence, feedback (MILESTONE C)
**Depends on:** 18. **Docs:** 08 s3.9, s4.
**Tasks:** wizard preset "Person without visible ID card" (special-case fields: schedule, active dates, min seconds, escalation rows, exemptions), ID checks page with evidence crops and confirm/false-alarm buttons, event detail shows "person without visible ID (please verify)" with the torso crops, live wall chip "no ID?" only for `not_wearing`, "can't tell" shown subtly, access rules for In-charge.
**Tests:** vitest for the sentence summary of the ID rule; Playwright: create the ID rule on a special zone, dry run on the entrance clip, mark a false alarm.
**Human checkpoint (Milestone C demo):** as in step 18 but entirely from the browser.
**Done when:** Phase C demo works end to end.

---
## PHASE D: FINISH

### Step 20: System health, benchmarks, retention
**Depends on:** 19. **Docs:** 07, 09 s4.5.
**Tasks:** retention job (classes, watermarks, protected/pinned safety, hourly, audited), integrity verifier (weekly), backup (if enabled), health page additions (worker status, queue drops, GPU, spot-check wrong-accepted rate with Wilson interval), `tools/bench.py` and `scripts/plot_bench.py` (1, 2, 3 cameras + simulated 4 to 6), storage estimate, event loop lag test.
**Tests:** retention decisions (pure) for each class; deleter refuses outside paths; never deletes protected/pinned; watermarks trigger in order; integrity mismatch flagged; Wilson interval maths; benchmark script runs on synthetic input.
**Human checkpoint:** run the benchmark; read the numbers; state honestly whether the targets in docs/01 s5 are met.
**Done when:** benchmark CSV/PNGs exist in `docs/results/`.

### Step 21: Hardening, demo and handover
**Depends on:** 20. **Docs:** all.
**Tasks:** graceful shutdown (no stray threads/FFmpeg), startup checks, DB integrity check on start, error pages, `docs/RESULTS.md` (all numbers from scripts with exact commands and data), `docs/USER_GUIDE.md` (admin steps with the wizard), `docs/DEMO_SCRIPT.md` (10 minute demo covering Milestones A, B, C, with fallbacks if a clip fails), seed script for demo data (`tools/seed_demo.py`, clearly marked synthetic), privacy checklist in the UI/README (TODO_department items), `README.md` (install, run, test, troubleshoot).
**Tests:** full backend and frontend suites; shutdown test; a fresh-clone install test following README on a clean venv; permission matrix complete; grep tests.
**Human checkpoint:** rehearse the demo from the script on a clean start.
**Done when:** the human can start the system and run the demo from README alone.
