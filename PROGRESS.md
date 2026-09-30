# PROGRESS.md (the agent updates this after every step)

Statuses: `NOT_STARTED`, `IN_PROGRESS`, `PARTIAL` (some required tests skipped), `PASSED (synthetic)`, `PASSED` (all tests run and pass; human notified), `BLOCKED` (see BLOCKED.md), `APPROVED` (set by the human only).

## Environment (agent fills at step 0)
| Item | Value |
|---|---|
| OS / Python | Windows / 3.11.9 |
| GPU, driver, torch + CUDA | NVIDIA GeForce RTX 4070 Ti, driver unknown, 2.14.0+cpu + False |
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
| 3 | Detection and tracking | NOT_STARTED | | | |
| 4 | Zones, attributes and rule engine (pure) | NOT_STARTED | | | |
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
| 2 | start MediaMTX, `fake_camera` for cam01, add the camera, see snapshot, kill the stream and watch status flip to offline then back.| Passed ||

## Measured results (only real numbers, with the command that produced them)
| Metric | Value | Command / script | Date |
|---|---|---|---|

## Step reports
(none yet)
