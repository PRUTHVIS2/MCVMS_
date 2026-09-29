# 05_VEHICLES.md (vehicle attributes, plates, registry, identity)

Guiding principle: **the AI may be unsure; a silently wrong plate is the worst outcome.** Everything uncertain goes to the review queue with evidence. Plate is the key of identity. Appearance only suggests.

## 1. Sighting lifecycle (`identity/sightings.py`, `pipeline/finalizer.py`)
A **sighting** is one vehicle track on one camera.
1. **Created** when a vehicle track has at least `vehicles.sighting.min_frames` frames and box height at least `analysis.min_vehicle_px` (full-res). Status `pending`.
2. **Provisional attributes** (category, colour, plate-so-far) are pushed to the rule engine at most once per second.
3. **Finalised** when the track has been lost for `analysis.lost_after_s`, or the track age exceeds `vehicles.sighting.max_sighting_s` (long parked vehicle: finalise once, flag `long_dwell`, no further clips for it).
4. The `SightingFinalizer` (waits up to `plate.finalize_wait_s` for late reads) votes the plate, matches, links identity, creates review items, writes the DB rows and sidecar, and requests the 10 s clip.
5. **Duplicate suppression (track id switches):** if a sighting for the same `vehicle_id` on the same camera ended less than `vehicles.sighting.dedupe_window_s` ago, it is still stored but linked to the same vehicle and gets **no new clip** (`flags.duplicate_of`).
Zones visited: on every tick the zone membership of the foot point is recorded (normal and special) into `zones_json`.

## 2. Attributes (`attributes/vehicle_attrs.py`, `vision/colour.py`)
- **category:** majority vote of the detector class over the track's frames, mapped through `models.class_map` (COCO car/motorcycle/bus/truck -> `car`/`two_wheeler`/`bus`/`truck`). Known only when at least `vehicles.category_vote_min_frames` frames and the winning share is at least 0.6. `auto_rickshaw` exists only when a custom class is in the model.
- **heavy:** `category in heavy_categories` (config, default truck and bus). Documented heuristic; a custom model may add classes like `heavy_truck` and `tempo`.
- **colour:** take the central region of the vehicle crop (drop the bottom `colour.crop_drop_bottom_frac` = 25 percent and any detected plate area), convert to HSV, take the dominant mass: `v < 0.25` black; `s < 0.15 and v > 0.75` white; `s < 0.15` grey_silver; else hue bins (red, orange_yellow, green, blue, brown). If the crop's mean `v < colour.night_v_threshold` return `unknown`. Vote across frames. Colour is used for grouping and soft warnings, **never for identity**.
- **body_type (optional, default OFF):** zero-shot with the appearance embedder against text prompts. Enable only after the human confirms accuracy on their footage (`attributes.body_type.enabled`). Never used for identity.

## 3. Plate pipeline (`plates/`)
Runs in `PlateWorker` (bounded queue, never blocks the analyzer).
1. **Scheduling:** for a vehicle track that passes the quality gate (box height at least `plate.min_vehicle_px`, inside the read area if one exists, not attempted more than every `plate.min_attempt_interval_s`, at most `plate.max_attempts_per_track` attempts, global budget `plate.budget_reads_per_s`), enqueue a job. A job holds a **crop of the vehicle from the full-resolution frame** plus `(ts, track_id, camera_id)`.
2. **Plate detection** in the vehicle crop with `models.plate_detector`. Keep boxes with confidence at least `plate.detector_conf` and aspect ratio in `[aspect_min, aspect_max]`. Crop with `plate.crop_pad_frac` padding.
3. **Quality gate:** plate width at least `plate.min_plate_w_px` and Laplacian-variance sharpness at least `plate.min_sharpness`; otherwise record a `low_quality` attempt (counted, not OCR'd).
4. **Preprocess** chain from `plate.preprocess` (`contrast`, `sharpen`, `upscale2x`, empty by default). `polarity_normalise: true` inverts light-on-dark plates (for example some commercial or EV plates) so OCR sees one polarity. Two-line plates (aspect below ~2.5): split at the middle, OCR each half, concatenate.
5. **OCR** through an `OcrEngine` interface (`read(image) -> (text, per_char_conf)`), default EasyOCR with an allowlist `A-Z0-9`, fallback engines listed in `plate.ocr_fallbacks`. A failed engine is skipped, logged once.
6. **Normalise and repair** (`plates/normalise.py`, pure): upper-case, strip non-alphanumerics; validate against Indian layouts in `plate.formats` (regexes: state code + 2 digits + 1 to 3 letters + 1 to 4 digits, plus Bharat series `YYBHNNNNXX`). Positional confusion repair by expected class (letter vs digit): `O<->0`, `I<->1`, `B<->8`, `S<->5`, `Z<->2`, `G<->6`, `D<->0`, `Q<->0`. Allow at most `plate.repair_max` (2) swaps, each multiplying confidence by `1 - plate.repair_penalty`. Return `(text, valid, repairs)`.
7. **Store each read** in `plate_reads` (`plate.store_read_crops` true keeps the crop).
8. **Voting** (`plates/voting.py`, pure function with unit tests): group reads by length after normalisation; take the length with the highest total confidence weight; per position take the confidence-weighted majority; `plate_conf` = mean position confidence times the repair factor. Require `vote_min_reads` (2) reads, or one read with conf at least `single_read_min_conf` (0.85); otherwise there is **no final plate**, but keep the partial pattern (positions with confidence at least 0.6, others `*`, at least 4 known characters).
9. **Best plate crop** = the read maximising `conf x min(1, sharpness/sharpness_ref) x min(1, plate_w_px/target_plate_w_px)`; saved as `plate_crop_path`.
Camera guidance: the read area should put plates at least `plate.min_plate_w_px` wide at full-res; `tools/plate_probe` measures this for a clip (histogram of plate widths, percentage of tracks with at least one qualifying plate) so the human can move the camera or zone **before** trusting results.

## 4. Registry matching and status (`matching/`)
Matching universe = active registry entries (valid dates) **plus** plates of vehicles already seen (`vehicles.plate`). Scoring:
- Weighted edit distance between the voted plate `S` (per-position confidences `c_i`) and each candidate `R`: match 0; substitution `sub_cost` (1.0) or `confusable_sub_cost` (0.3) for pairs in the confusion map, times `w_i = 0.4 + 0.6*c_i`; deleting a char of `S` costs `indel_cost*w_i`; inserting one missing from `S` costs `indel_cost`. `score = clamp(1 - distance/max(len(S),len(R)),0,1)`.
- Keep top `matching.top_k` (3) with score at least `candidate_min` (0.50). With only a partial pattern, score against the pattern (unknown positions cost 0).
- **Decision** (`matching/tiers.py`, pure `decide(plate_result, candidates) -> Decision`):

| Condition | status | match_type |
|---|---|---|
| exact match and `plate_conf >= exact_conf_min` (0.80) | `resolved` | exact |
| top score >= `auto_accept_score` (0.90) and lead over 2nd >= `margin_min` (0.10) | `resolved` | fuzzy |
| exact with conf in [0.60, 0.80), or top score >= `fuzzy_score_min` (0.75) with margin | `verify` | exact/fuzzy |
| valid-format plate, `plate_conf >= unregistered_conf_min` (0.75), no candidate >= `candidate_min` | `unregistered` | none |
| anything else: no plate, invalid format, low confidence, ambiguous | `needs_review` | none |

`resolved`/`verify`/`unregistered` all carry a plate, so all three can be linked to a vehicle identity; `verify` shows in a "please verify" list, `needs_review` enters the review queue. **Loosening any threshold requires measured evidence in `docs/results/`.**
- **Spot checks:** a random `review.spot_check_rate` (5 percent) of `resolved` sightings also creates a low-priority review item (`spot_check`, no alert). Admin results produce the measured **wrong-accepted rate** on the System page (Wilson 95 percent interval once at least 30 samples exist).
- **Type mismatch flag:** if a registry match exists and observed category (known, conf >= 0.7, at least 5 frames) differs in group (two_wheeler/car/bus/truck) from the registered category, set `flags.category_mismatch` and raise a low alert `plate_mismatch`. Colour mismatch alone never alerts.
- Registry edits never silently change past sightings. `POST /registry/rematch` re-evaluates only `unregistered`/`needs_review` sightings of the last 7 days (admin-triggered, audited).

## 5. Vehicle identity across cameras and days (`identity/`)
Goal: one `vehicles` row per real vehicle, found by any camera, any day.
1. **By plate (authoritative).** After matching, if the sighting has a final plate (status `resolved`, `verify` or `unregistered`): `get_or_create_vehicle(plate)`. Registry-linked plates set `registry_id`. Set `link_type=plate`. Different cameras or days with the same plate map to the same vehicle automatically. Update `first_seen`, `last_seen`, `sightings_count`, and the most common `category`/`colour`.
2. **Near-duplicate plates (ghost prevention).** If a new plate is not exactly equal to any vehicle but its weighted score against an existing vehicle plate is at least `identity.link_by_plate_fuzzy_score` (0.90) with the margin rule, do NOT create a new vehicle; link to the existing one with `link_type=plate`, `match_type=fuzzy` and status `verify`. Otherwise create a new vehicle only when the plate is valid-format and `plate_conf >= unregistered_conf_min`.
3. **No plate: appearance candidates only.** For a `needs_review` sighting, compute an appearance embedding of the best vehicle crop (`identity.embedder`, L2-normalised). Compare against embeddings of vehicles seen in the last `identity.appearance_window_h` with the same category and compatible colour. Candidates with cosine score at least `identity.appearance_min_score` and margin over the next best at least `identity.appearance_margin` are shown in the review item (`reason=appearance_candidate`, shown as "possible: V-000123, 91 percent"). **Never auto-linked.** The admin can accept (link_type=admin) or ignore.
4. **Merge / split.** Admin can merge two vehicles (for example a plate fixed later) or split selected sightings off. Audited, reversible for 30 days.
5. **Embedder choice is a decision gate inside step 14:** compare at most two options on the human's labelled cross-camera pairs (same vehicle vs different vehicle): (a) OpenCLIP image encoder (verify licence and availability), (b) a vehicle re-ID checkpoint trained on a public dataset if a suitable, permissively licensed one exists. Report ROC/AUC and the score threshold that gives 5 percent false-candidate rate. Record in `docs/DECISIONS.md`. If neither is useful on real footage, disable appearance candidates and say so; plate identity still works.
6. Persistent across days: vehicles and sightings metadata are kept `retention.metadata_days` (default 365). Clips expire earlier (docs/07).

## 6. The 10 s sighting clip (`recorder/clipper.py`, kind `sighting`)
- One clip per finalised sighting (unless duplicate-suppressed, section 1.5, or another sighting-clip for the same vehicle+camera exists within `clips.sighting.min_gap_s_same_vehicle_camera`, 60 s).
- Length exactly `clips.sighting.length_s` (10 s). Anchor time = timestamp of the best plate crop if any, else the time the track was closest/largest. Window = `[anchor - pre_s, anchor + (length_s - pre_s)]` (`pre_s` = 4), shifted to stay within the recorded segments.
- Re-encoded to H.264 (`h264_nvenc`, fallback `libx264`) so browsers play it; audio removed; frame-accurate. Key frames (first sight, best plate, last sight) saved as JPEG next to it. Sidecar `meta.json` holds the sighting summary.
- If the segments are not yet on disk (cutting too early) wait until they are; if the source segments are already deleted the clip is `failed` with a reason.

## 7. Review queue (`services/review.py`)
One review item per sighting at most. Created by the finalizer:
| Sighting situation | reason | priority | alert |
|---|---|---|---|
| no plate read | `no_plate` | 50 | low `unresolved_plate` |
| low confidence | `low_confidence` | 60 | low `unresolved_plate` |
| ambiguous candidates | `ambiguous` | 70 | low `unresolved_plate` |
| invalid layout | `invalid_format` | 55 | low `unresolved_plate` |
| appearance candidates exist | `appearance_candidate` | 40 | none |
| selected as spot check | `spot_check` | 5 | none |
`due_at` = today at `review.deadline_local` (18:00), or tomorrow if created later. The sighting's clip is `protected` until resolved. **Admin actions** (audited, one transaction): confirm candidate 1/2/3; correct the plate (normalise, validate, match); register as new vehicle (prefilled form -> registry entry + vehicle); mark visitor (registry entry `kind=visitor` with validity); link to a suggested vehicle; dismiss (not a vehicle / duplicate / other, reversible); skip. After a plate is set: recompute the vehicle link, save a `training_samples` row (best plate crop + text), resolve the item and its alert. Spot-check items offer only "correct" / "wrong: enter the right plate".

## 8. Vehicle alerts (in addition to rule events)
| Level | kind | Message | Trigger |
|---|---|---|---|
| low | `unresolved_plate` | `Plate not identified · {camera} · {HH:MM}` | each review item except spot check/appearance |
| low | `plate_mismatch` | `Plate {plate} seen on a {observed}, registered as {registered}` | section 4 |
| low | `review_digest` | `{n} vehicles still need review (due {HH:MM})` | at the deadline if pending |
| low | `review_overdue` | `{n} review items overdue` | next morning `review.reminder_local` |
| medium | `camera_offline` | `{camera} offline since {HH:MM}` | health |
No flooding: at most one open alert per (kind, target). Dismissal requires a reason.

## 9. Training samples
When an admin confirms or corrects a plate, save `(best_plate_crop, text)` into `training_samples`. Split by sighting date: dates in `training.test_dates` (frozen test set) go to `test`, others by hash into train/val. Export with `python -m app.tools.export_training`. These crops improve the OCR/detector later.

## 10. Failure behaviour
| Failure | Behaviour |
|---|---|
| plate weights missing | plate reading disabled, warning, all sightings `needs_review` (reason `no_plate`), category/colour/clip still recorded |
| OCR engine error | fall back to the next engine, else as above |
| PlateWorker queue full | drop oldest job, count `plate_queue_drops` |
| no read in whole sighting | `needs_review`, `no_plate` |
| registry empty | every valid confident plate is `unregistered`; system warning "registry is empty" |
| embedder missing | no appearance candidates; plate identity unaffected |
