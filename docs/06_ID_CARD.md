# 06_ID_CARD.md ("person without a visible ID card")

## 1. What this feature is (and is not)
It reports **"person without visible ID"**, with evidence, so a human can check. It cannot tell students from staff or visitors, and it cannot prove a card is absent, only that it was not visible in several good views. Therefore the pipeline has three states and only one of them can alert:

| `id_state` | Meaning | Can trigger an alert |
|---|---|---|
| `wearing` | a card/lanyard was clearly seen | no |
| `not_wearing` | several good frontal views, none showing a card | yes |
| `unknown` | not enough good views (back turned, torso occluded, too small, blurred) | **never** |

## 2. Camera and zone guidance (tell the human in the UI)
- Works only where people approach the camera and the **torso is large enough**: entrances, turnstiles, corridors ending at the camera, typically 3 to 6 m, mounted around 2.5 m, angled slightly down, no strong back-light.
- `python -m app.tools.id_probe --clip X.mp4` reports the distribution of torso pixel width and the share of tracks with at least `id_check.min_good_frames_probe` good frames. If most tracks never get a good frame, the camera cannot support this feature, and the report says so plainly.
- Draw the zone where people are already large and facing the camera; the ID state is accumulated **along the whole track** (also before entering the zone), so approach frames count.

## 3. Pipeline (`vision/pose.py`, `attributes/id_state.py`, `PoseIdWorker`)
1. **Person + keypoints:** on `id_check` cameras the pose model (`models.person_pose`) is the person detector and gives 17 COCO keypoints. ByteTrack tracks persons. Keypoints are in full-res coordinates.
2. **Needs check (lazy):** run the ID steps only for person tracks that are in, or within `id_check.approach_margin_px` of, a zone that has an armed, in-schedule rule referencing `id_state`, and only while the track's `id_state` is not yet final.
3. **Torso crop (`vision/crops.py`, from the full-res frame):** using shoulders (5,6) and hips (11,12): region between the shoulder line and the hip midpoint, widened by `id_check.torso_pad_frac` (0.25) horizontally, extended upward `0.1 x` shoulder-hip length to include the lanyard neck loop; resized to `id_check.classifier_input` (160x160). If hips are not visible use shoulders plus an estimated length of `1.3 x` shoulder width.
4. **Per-frame quality gate** (frame counts as GOOD only if all hold): shoulder keypoint confidence at least `shoulder_conf_min`; box height at least `analysis.min_person_px`; torso width at least `min_torso_px`; frontal enough: `shoulder_width / torso_height >= frontal_ratio_min`; sharpness (Laplacian variance) at least `blur_min`; the torso is not mostly covered by another person's box (`occlusion_iou_max`). At most one good frame is used per `good_frame_min_interval_s`.
5. **Classifier** (`models.id_classifier`, Ultralytics classification model, 3 classes): `id_visible`, `no_id_visible`, `unusable` (bag, hands, jacket, or otherwise not decidable). Frames the classifier calls `unusable` with probability at least `unusable_p_min` are dropped from the good set.
6. **Aggregation** (`attributes/id_state.py`, pure function `resolve(frames, cfg) -> IdResult`), over the good frames of the track so far:
   - `wearing` if at least `wear_min_frames` (2) good frames have `p(id_visible) >= wear_p_min` (0.70). Sticky: once `wearing`, always `wearing` for the track (one clear card beats any number of misses).
   - `not_wearing` only if ALL hold: at least `absent_min_good_frames` (8) good frames; they span at least `absent_min_span_s` (1.0 s); `max p(id_visible) < absent_p_id_max` (0.30); `mean p(no_id_visible) >= absent_p_no_id_mean_min` (0.70).
   - otherwise `unknown` with a `reason` (`too_few_good_frames`, `short_span`, `ambiguous`, `back_or_occluded`).
   `not_wearing` can be overturned to `wearing` if later evidence arrives before the track ends (event updates to `false_alarm_auto`; the alert is retracted and marked `expired` if it is still open).
7. **Output:** `id_state` attribute (value + confidence = `p_no_id_mean`), written when the state changes. On track end an `id_checks` row is saved with counts, reason, and up to `id_check.evidence_crops` (5) torso crops plus one snapshot to `evidence_dir` (`retention.id_evidence_days`, short).
8. **Rule engine** sees only `id_state`. "No ID card" is a normal registered action (docs/04): zone, `where id_state eq not_wearing`, `presence` with `min_seconds`, schedule, valid dates, exemptions, severity, escalation.

## 4. Special cases the admin can set
| Case | How |
|---|---|
| Only during entry hours | rule `schedule` |
| Rule active from/until a date | `valid` |
| Holidays, exam days, events | `calendar_exemptions` selected in the rule |
| Ignore tiny/far people | `subject.min_box_px` |
| Alert only after N seconds in zone | `trigger.min_seconds` |
| Repeats: many people without ID | `escalation` with `if_count_in_window` |
| Do not re-alert the same person walking around | `cooldown_s` per track (no identity is stored across tracks) |
| Known lanyard colour (staff/visitor exemption) | optional resolver `lanyard_colour`, OFF by default; enable only if the human confirms a colour scheme; a person whose lanyard colour is on the allowlist gets `id_state=wearing` with reason `lanyard_allowlist` |
The system never remembers a person across tracks or days. Repeat-offender tracking is out of scope (needs biometrics).

## 5. Dataset and training tools (human collects, agent builds the tooling)
- `python -m app.tools.extract_torso_crops --clip X.mp4 --out dataset/id_raw` runs pose + torso cropping with the same code as production, saving crops with a manifest (clip, track, frame, quality flags).
- Human sorts crops into `dataset/id/train|val|test/{id_visible,no_id_visible,unusable}/` (class-per-folder). **Split by person/clip, never by frame**, or the test numbers are meaningless. Provide `scripts/split_dataset.py` that enforces clip-level splits from the manifest.
- `python scripts/train_id_classifier.py --data dataset/id --epochs N` fine-tunes an Ultralytics classification model and saves to `data/models/id_cls.pt` with a metrics JSON. Verify the exact CLI/API of the installed ultralytics version first.
- Guidance to show the human: aim for balanced classes, varied clothing, lighting, distances; include hard negatives (card flipped, card in hand, bag strap, dark lanyard on dark clothing); at least a few hundred crops per class to start, more is better; a frozen test set of different people.
- Feedback loop: when an admin marks an alert `false_alarm`, its evidence crops are copied to `dataset/id_feedback/false_alarm/` (local only, audited) for relabelling and retraining.

## 6. Evaluation (`scripts/id_baseline.py`, step 17 gate)
Ground truth: `test_data/id/id_ground_truth.csv` (one row per person track in a labelled clip: clip, start_s, end_s, description, expected `wearing`/`not_wearing`/`unclear`, view, light). Run the production tracker + resolver in batch mode, match predicted tracks to labelled ones by time overlap and position, and report a **confusion matrix** of expected vs predicted (`wearing`, `not_wearing`, `unknown`), with breakdowns by `view` and `light`, and these headline numbers:
- **False-accusation rate:** expected `wearing`, predicted `not_wearing` (goal 5 percent or less).
- **not_wearing precision** and **recall on good-view tracks**.
- **Unknown rate** overall and per view.
Also the classifier's own confusion matrix on the frozen frame-level test set. If numbers miss goals: report, then the human decides (more data, camera move, or trying a detector fine-tune for `id_card`/`lanyard` classes; agent proposes, human adds a step to PLAN). **Never tune `wear_p_min`/`absent_*` on the test set.**

## 7. Failure behaviour and privacy
| Failure | Behaviour |
|---|---|
| ID classifier weights missing | feature disabled with a banner; every person `id_state=unknown`; no alerts |
| pose model missing | same |
| worker queue full | drop oldest, count `id_queue_drops`; state stays `unknown` |
Privacy: torso crops and snapshots are personal data, kept only for alerts and audit (`retention.id_evidence_days`, default 30), visible to Admin and Owner (In-charge sees the alert and the clip only if allowed by the department's policy setting `privacy.incharge_can_view_id_clips`, default false). No face crops are saved deliberately (torso crops exclude the head). No identity is stored.
