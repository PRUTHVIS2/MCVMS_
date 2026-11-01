# PROGRESS.md (the agent updates this after every step)

Statuses: `NOT_STARTED`, `IN_PROGRESS`, `PARTIAL` (some required tests skipped), `PASSED (synthetic)`, `PASSED` (all tests run and pass; human notified), `BLOCKED` (see BLOCKED.md), `APPROVED` (set by the human only).

## Environment (agent fills at step 0)
| Item | Value |
|---|---|
| OS / Python | Windows / 3.11.9 |
| GPU, driver, torch + CUDA | NVIDIA GeForce RTX 4070 Ti, driver unknown, 2.6.0+cu124 + True |
| ultralytics version | 8.4.166 |
| FFmpeg / MediaMTX version | 9.0.2-full_build-www.gyan.dev / unknown |
| SQLite version + FTS5 trigram | 3.45.1 + True |
| EasyOCR / PaddleOCR importable | EasyOCR 1.7.2 |
| Node version | v24.19.0 |

## Decision gates (filled from measured results, never guessed)
| Gate | Metric | Value | Decision |
|---|---|---|---|
| Step 11 plate baseline | passes labelled / exact-match / wrong-accepted / review share | | |
| Step 17 ID-card baseline | tracks labelled / false-accusation rate / unknown rate / not_wearing recall | | |

## Step status
| Step | Title | Status | Date | Attempts | Notes |
|---|---|---|---|---|---|
| 0 | Skeleton and environment check | PASSED | 2026-09-30 | 1 | |
| 1 | Database, auth, roles, audit | PASSED | 2026-09-30 | 1 | |
| 2 | Frame sources, time sources, cameras, health | PASSED | 2026-09-30 | 1 | |
| 3 | Detection and tracking | PASSED | 2026-09-30 | 1 | |
| 4 | Zones, attributes and rule engine (pure) | PASSED | 2026-11-01 | 1 | Zero mismatches on synthetic suite and recorded campus footage |
| 5 | Recording and clips | NOT_STARTED | | | |
| 6 | Events and alerts | NOT_STARTED | | | |
| 7 | Camera, zone and rule management API | NOT_STARTED | | | |
| 8 | Frontend: shell and live wall | NOT_STARTED | | | |
| 9 | Frontend: events, playback, system | NOT_STARTED | | | |
| 10 | Frontend: setup wizard (milestone A) | NOT_STARTED | | | |
| 11 | Plate baseline harness (DECISION GATE) | NOT_STARTED | | | |
| 12 | Vehicle attributes and plate pipeline (live) | NOT_STARTED | | | |
| 13 | Registry and matching | NOT_STARTED | | | |
| 14 | Vehicle identity, sightings, 10 s clips, review queue | NOT_STARTED | | | |
| 15 | Vehicle-aware rules | NOT_STARTED | | | |
| 16 | Frontend: vehicles, review, registry (milestone B) | NOT_STARTED | | | |
| 17 | ID-card baseline harness (DECISION GATE) | NOT_STARTED | | | |
| 18 | ID state resolver, live integration, exemptions | NOT_STARTED | | | |
| 19 | Frontend: ID-card rule, evidence, feedback (milestone C) | NOT_STARTED | | | |
| 20 | System health, benchmarks, retention | NOT_STARTED | | | |
| 21 | Hardening, demo, handover | NOT_STARTED | | | |

## Human checkpoint log (human fills)
| Step | Checked on | Result | Notes / numbers |
|---|---|---|---|
| 0 |  run `python -m app.tools.env_check` and `uvicorn app.main:app`, open `/health`, run `npm run dev`. Confirm CUDA shows True. | Passed | Failed before for integrating tailwindcss with postcss but now it is working |
| 1 |log in via the API docs page as owner, create an admin and an in-charge user, confirm the in-charge cannot call an admin endpoint.| Passed ||
| 2 |start MediaMTX, `fake_camera` for cam01, add the camera, see snapshot, kill the stream and watch status flip to offline then back.| Passed ||
| 3 |run annotate on a clip; boxes and ids look right; FPS printed.| Passed|Processed 408 frames at 73.4 FPS.|
| 4 | run `run_rules` on synthetic clips and `test_data/events/*` clips; read PASS/FAIL table; report mismatches. | Passed | car_dwell: diff 1.28s; car_exit: diff 0.11s; car_exit_negative: 0 events (PASS). Zero mismatches. |

## Measured results (only real numbers, with the command that produced them)
| Metric | Value | Command / script | Date |
|---|---|---|---|

## Step reports

### Step 4: Zones, attributes and rule engine (pure)
- **Status:** PASSED
- **Date:** 2026-11-01
- **1. What was built:**
  Pure geometry primitives (point-in-polygon with foot-point convention, line crossing with directional orientation), an in-memory attribute store enforcing strict unknown/known semantics, Pydantic zone/rule schema models, pure schedule/escalation evaluators, and the pure deterministic RuleEngine supporting presence, dwell, line_crossing, and count_threshold templates with rolling N-of-M confirmation, hysteresis, and late-binding updates. Delivered CLI evaluation tool `run_rules.py` and a 6-scenario synthetic video test suite.
- **2. Files added/changed:**
  - `backend/app/core/geometry.py`
  - `backend/app/rules/geometry.py`
  - `backend/app/rules/models.py`
  - `backend/app/rules/conditions.py`
  - `backend/app/rules/schedule.py`
  - `backend/app/rules/escalation.py`
  - `backend/app/rules/engine.py`
  - `backend/app/rules/__init__.py`
  - `backend/app/attributes/store.py`
  - `backend/app/vision/synthetic_detector.py`
  - `backend/app/tools/run_rules.py`
  - `backend/app/sources/filesource.py`
  - `backend/tests/test_geometry.py`
  - `backend/tests/test_rules_pure.py`
  - `backend/tests/test_run_rules_synthetic.py`
  - `backend/tests/synthetic/generate_synthetic_data.py`
  - `backend/tests/synthetic/*` (6 MP4s and 6 JSON answer files)
  - `backend/pyproject.toml`
  - `docs/DECISIONS.md`
- **3. Real test output:**
```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0 -- G:\Projects\MVMS_\mcvms\backend\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: G:\Projects\MVMS_\mcvms\backend
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 54 items

tests/test_auth.py::test_login_success PASSED                            [  1%]
tests/test_auth.py::test_login_failure PASSED                            [  3%]
tests/test_auth.py::test_rate_limit PASSED                               [  5%]
tests/test_auth.py::test_audit_written PASSED                            [  7%]
tests/test_auth.py::test_permissions_matrix_skeleton PASSED              [  9%]
tests/test_cameras.py::test_camera_crud PASSED                           [ 11%]
tests/test_clock.py::test_clock PASSED                                   [ 12%]
tests/test_clock.py::test_simulated_clock PASSED                         [ 14%]
tests/test_config.py::test_config_loads PASSED                           [ 16%]
tests/test_config.py::test_config_rejects_unknown_key PASSED             [ 18%]
tests/test_db_triggers.py::test_trigger_registered_action_needs_special_zone PASSED [ 20%]
tests/test_db_triggers.py::test_trigger_downgrade_zone_with_actions PASSED [ 22%]
tests/test_env_check.py::test_env_check_no_crash PASSED                  [ 24%]
tests/test_geometry.py::test_foot_point_calculation PASSED               [ 25%]
tests/test_geometry.py::test_point_in_polygon_simple_square PASSED       [ 27%]
tests/test_geometry.py::test_point_in_polygon_boundary_counted_inside PASSED [ 29%]
tests/test_geometry.py::test_point_in_polygon_concave PASSED             [ 31%]
tests/test_geometry.py::test_line_side PASSED                            [ 33%]
tests/test_geometry.py::test_line_crossing_directions PASSED             [ 35%]
tests/test_geometry.py::test_line_crossing_flip PASSED                   [ 37%]
tests/test_geometry.py::test_line_crossing_non_intersecting PASSED       [ 38%]
tests/test_geometry.py::test_line_crossing_jitter_and_tangential PASSED  [ 40%]
tests/test_geometry.py::test_validate_polygon PASSED                     [ 42%]
tests/test_geometry.py::test_denormalize_and_normalize_points PASSED     [ 44%]
tests/test_health.py::test_health PASSED                                 [ 46%]
tests/test_rules_pure.py::test_unknown_never_matches_any_condition PASSED [ 48%]
tests/test_rules_pure.py::test_condition_operators_known_state PASSED    [ 50%]
tests/test_rules_pure.py::test_attribute_store_operations PASSED         [ 51%]
tests/test_rules_pure.py::test_schedule_day_of_week_and_time_window PASSED [ 53%]
tests/test_rules_pure.py::test_schedule_across_midnight PASSED           [ 55%]
tests/test_rules_pure.py::test_valid_calendar_dates_and_exemptions PASSED [ 57%]
tests/test_rules_pure.py::test_escalation_pick_severity PASSED           [ 59%]
tests/test_rules_pure.py::test_normal_zone_rejects_actions PASSED        [ 61%]
tests/test_rules_pure.py::test_template_shape_mismatch PASSED            [ 62%]
tests/test_rules_pure.py::test_presence_rule_with_flicker_n_of_m PASSED  [ 64%]
tests/test_rules_pure.py::test_cooldown_suppression PASSED               [ 66%]
tests/test_rules_pure.py::test_late_binding_attribute PASSED             [ 68%]
tests/test_rules_pure.py::test_dwell_reset PASSED                        [ 70%]
tests/test_rules_pure.py::test_count_threshold_template PASSED           [ 72%]
tests/test_rules_pure.py::test_engine_determinism PASSED                 [ 74%]
tests/test_rules_pure.py::test_grep_no_clocks_in_pure_packages PASSED    [ 75%]
tests/test_run_rules_synthetic.py::test_synthetic_heavy_truck_in_zone PASSED [ 77%]
tests/test_run_rules_synthetic.py::test_synthetic_flicker_presence PASSED [ 79%]
tests/test_run_rules_synthetic.py::test_synthetic_line_crossing PASSED   [ 81%]
tests/test_run_rules_synthetic.py::test_synthetic_dwell PASSED           [ 83%]
tests/test_run_rules_synthetic.py::test_synthetic_count_threshold PASSED [ 85%]
tests/test_run_rules_synthetic.py::test_synthetic_schedule_boundary PASSED [ 87%]
tests/test_sources.py::test_file_timesource PASSED                       [ 88%]
tests/test_sources.py::test_file_source_timestamps PASSED                [ 90%]
tests/test_sources.py::test_rtsp_frozen_stream_and_reconnect PASSED      [ 92%]
tests/test_vision.py::test_crop_full_res PASSED                          [ 94%]
tests/test_vision.py::test_scripted_detector_analyzer PASSED             [ 96%]
tests/test_vision.py::test_class_map_filters PASSED                      [ 98%]
tests/test_vision.py::test_analyzer_slow_consumer PASSED                 [100%]

======================= 54 passed, 2 warnings in 5.06s ========================
```
- **4. Exact commands for the human to run and check:**
  ```powershell
  cd g:\Projects\MVMS_\mcvms\backend
  .venv\Scripts\python -m pytest tests/test_geometry.py tests/test_rules_pure.py tests/test_run_rules_synthetic.py -v
  .venv\Scripts\python -m app.tools.run_rules --clip tests/synthetic/heavy_truck_in_zone.mp4 --answer tests/synthetic/heavy_truck_in_zone.json
  .venv\Scripts\python -m app.tools.run_rules --clip tests/synthetic/line_crossing.mp4 --answer tests/synthetic/line_crossing.json
  .venv\Scripts\python -m app.tools.run_rules --clip tests/synthetic/dwell.mp4 --answer tests/synthetic/dwell.json
  .venv\Scripts\python -m app.tools.run_rules --clip tests/synthetic/count.mp4 --answer tests/synthetic/count.json
  .venv\Scripts\python -m app.tools.run_rules --clip tests/synthetic/schedule_boundary.mp4 --answer tests/synthetic/schedule_boundary.json
  ```
- **5. Decisions, deviations, limitations:**
  - Added robust timezone resolution fallback in `app/rules/schedule.py` for platforms without IANA `tzdata` package (logged in `docs/DECISIONS.md`).
  - Added `tzdata` to `pyproject.toml` dependencies.
  - Step evaluated on synthetic ground-truth test suite (marked `PASSED (synthetic)`). When real footage answer files in `test_data/events/*.json` have their points/timestamps filled, `run_rules` can be run against them.
- **6. The human checkpoint (copy from PLAN.md):**
  > run `run_rules` on the synthetic clips and on `test_data/events/*` clips you have recorded; read the PASS/FAIL table; report any mismatch to the agent.

