# 09_TESTING.md

## 1. Levels
1. **Unit (pure, no GPU):** geometry, rule engine, escalation, schedule, plate normalise/voting, weighted edit distance and tiers, ID aggregation, retention decisions. Fast, deterministic, run everywhere.
2. **Synthetic pipeline:** scripted detectors emit tracks with attributes; generated videos (`tools/fake_camera`, `tools/make_synthetic_clip`) with coloured boxes moving along known paths; simulated clock. Proves rules, sightings, finalizer, clips.
3. **Integration (markers `integration`, `gpu`):** FFmpeg, MediaMTX, real weights, real clips. Skipped with a reason when unavailable.
4. **Evaluation on real footage (scripts):** produce numbers for the report. Never mixed into CI-style tests.
5. **Frontend:** vitest for logic (rule summary sentence, geometry helpers), Playwright smoke (login, draw zone, special-zone gating, create rule, dry run).

## 2. Always-true checks (run every step)
- `test_no_time_time_in_pure_packages` (grep `time.time`/`datetime.now` in `rules/`, `attributes/`, `matching/`, `plates/voting.py`, `plates/normalise.py`).
- Permission matrix over every endpoint x role (`tests/test_permissions.py`, table from `docs/08`).
- `test_normal_zone_rejects_actions` at API and raw-SQL trigger level.
- `test_names_hidden_for_incharge` over every response model containing a registry owner.
- `test_plate_never_logged_above_debug` (log capture).
- Unknown never matches (rule engine + attribute store).
- Event loop lag test: p95 under 100 ms while two scripted pipelines run.
- Shutdown test: no stray threads or FFmpeg processes.
- Retention safety: the deleter refuses paths outside data dirs and never deletes protected or pinned clips.
- Idempotence: finalizer run twice on the same track creates one sighting; review digest; rematch.
- `crop_full_res` returns exact pixels for a known pattern (plates and torso crops must come from full-res).

## 3. Ground-truth formats (human supplied, read-only for the agent)
### 3.1 Event answers (`test_data/events/*.json`)
See `test_data/events/README.md`. Zones and rules are given inside each JSON so the test builds them itself.
### 3.2 Vehicle passes (`test_data/vehicles/passes_ground_truth.csv`)
One row per vehicle passing a camera: `clip, camera, pass_no, approx_time_s, true_plate, plate_readable (yes|partial|no), category, colour, view (front|rear|side), light (day|dusk|night), direction (in|out|na), notes`. `true_plate` blank when unreadable; write the visible characters you are sure of and `*` for others in `notes`.
`test_data/vehicles/registry_test.csv` lists some (not all) of the true plates as registered (so both `registered` and `unregistered` outcomes are exercised) plus 2 to 3 decoy near-miss plates.
Cross-camera pairs: `test_data/vehicles/cross_camera_pairs.csv`: `clip_a, pass_a, clip_b, pass_b, same_vehicle (yes|no)` for the embedder comparison (at least 30 same, 60 different).
### 3.3 ID-card tracks (`test_data/id/id_ground_truth.csv`)
See `test_data/id/README.md`.

## 4. Metrics
### 4.1 Rule engine (per clip)
Expected events found (start time within `tolerance_s`), false events, duplicate events, end time accuracy; overall precision/recall.
### 4.2 Plates (`scripts/plate_baseline.py`)
Per sighting status vs truth:
| Metric | Definition |
|---|---|
| Exact read rate | final plate equals truth (among `plate_readable=yes`) |
| Wrong-accepted rate | status `resolved` (or `verify`) but plate differs from truth (the number that matters) |
| Safe-failure rate | among sightings the system got wrong or could not read, share that ended `needs_review` |
| Review load | share of all sightings in `needs_review` |
| Top-3 hit rate | among `needs_review` whose true plate is registered, share with the truth in the top 3 |
| Unregistered precision/recall | against plates left out of the registry |
| Partial credit | fraction of known characters matched on `partial` rows |
| Plate detector | precision, recall, mAP50 on plate test frames |
Every table is broken down by `category`, `view`, `light` first (one overall number hides failures).
### 4.3 Vehicle identity
Cross-camera linking on labelled pairs: how many same-vehicle pairs share one `vehicle_id` (via plate), how many different vehicles were wrongly merged (must be 0), and embedder ROC/AUC (step 14).
### 4.4 ID card (`scripts/id_baseline.py`)
Confusion matrix (expected vs predicted: wearing / not_wearing / unknown), false-accusation rate, not_wearing precision and recall on good views, unknown rate, breakdown by view and light; frame-level classifier confusion matrix on the frozen test set.
### 4.5 Latency and scale (`tools/bench.py`, `scripts/plot_bench.py`)
Stamps in `docs/02` section 10. p50/p95/max of `t_rule_fired -> t_alert_sent` and `t_rule_fired -> t_clip_ready`, analysis FPS per camera, plate attempts per second, queue drops, GPU/CPU/RAM. Run with 1, 2 and 3 cameras (plus 4 to 6 simulated with duplicated file streams). Outputs `docs/results/bench_<date>.csv` + PNGs. State that camera encode and network delay are excluded.

## 5. Decision gates
### Gate 1 (step 11): plate baseline
1. Human records at least 100 vehicle passes at the intended camera position(s) and fills the ground-truth CSV (plus `registry_test.csv`).
2. Agent runs `plate_probe` and `plate_baseline.py` with off-the-shelf detector + OCR, writes `docs/results/plate_baseline_<date>/`.
3. Agent proposes (evidence-based): proceed as is; move camera/read area; add preprocess steps and re-run to see which help; fine-tune plate detector; fine-tune OCR on collected crops. **Human decides.** Record decision and numbers in `PROGRESS.md` and `docs/DECISIONS.md`. Never tune thresholds without this data.
### Gate 2 (step 17): ID-card baseline
1. Human records the entrance footage and fills `id_ground_truth.csv`; collects and sorts torso crops (`docs/06` section 5).
2. Agent runs `id_probe`, trains the classifier with `scripts/train_id_classifier.py`, runs `id_baseline.py`, writes `docs/results/id_baseline_<date>/`.
3. If the false-accusation rate goal is missed, the agent proposes options (more data, better camera position, detector fine-tune). Human decides. If the camera cannot see torsos at all (probe), the honest result is "not feasible at this camera" and the feature is demonstrated at a better camera position.

## 6. Reporting rule
Every evaluation script writes `docs/results/<name>.json` plus plots; `docs/RESULTS.md` (step 21) summarises numbers with the exact command and data used. **Never include a number that was not produced by a script in this repository.**
