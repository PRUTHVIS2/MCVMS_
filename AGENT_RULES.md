# AGENT_RULES.md (read first, every session)

You are building **MCVMS**: a multi-camera video management system with two headline capabilities, both driven by **zones and registered actions**:

- **A. Vehicle intelligence.** Detect vehicles, read plates, record type/colour/plate + metadata into a persistent store, keep one identity per vehicle across cameras and days, save a 10 s clip per sighting, and let admins register rules such as "no heavy truck in this zone at this time".
- **B. No-ID-card alerts.** In a zone the admin draws, alert when a person is confidently **not wearing a visible ID card**, with severity levels and special cases.

The spec is `docs/01` to `docs/09`. The order of work is `PLAN.md`. The human is a student following a guide. They run the checkpoints and make the git commits.

## 1. Read order (every new session)
1. `AGENT_RULES.md` (this file)  2. `PROGRESS.md`  3. `PLAN.md` (the current step plus its "Depends on")  4. the `docs/` files that step references.
`docs/` says WHAT to build. `PLAN.md` says the ORDER and the acceptance tests. If they conflict, STOP and ask.

If the human says "do not write code yet": write no code. Reply with a summary (about 15 lines) of what you will build and in what order, list conflicts, gaps and risks you found in the documents, and state the Python version, GPU and OS you detected.

## 2. The gate (hard rule)
1. Do only the step the human names ("Do PLAN.md step N"). Never start the next step on your own.
2. Implement the tasks, run the step's tests, and ALSO re-run ALL earlier tests (regression).
3. "Passed" means you pasted the real command and its real output (last 40 lines minimum) into `PROGRESS.md`. Never write "tests pass" unless you ran them and saw them pass.
4. A test that cannot run here (no GPU, no MediaMTX, no weights, no footage) is marked `SKIPPED (reason)`. A step with skipped required tests is `PARTIAL`, not `PASSED`. Tests that rely only on synthetic data are marked `PASSED (synthetic)` and must be re-run when real footage exists.
5. When the step passes: update `PROGRESS.md` (status, date, files, test output, how the human runs and checks it, limitations, decisions) and STOP. Say when it is a good moment to commit. Wait for "Step N is approved".

## 3. Retry limit
If a test fails: read the error, form a hypothesis about the ROOT CAUSE, then change code. Maximum **3 fix attempts** per failing test. After the third failure write `BLOCKED.md` (step, failing test, full error, what you tried, best hypothesis, 2 options for the human) and STOP. Do not hack around it.

## 4. Protected things (never without explicit human approval)
- Never delete, skip, loosen or special-case a test, tolerance or threshold. Never hard-code expected values from a test or a clip name into production code.
- Never edit anything in `test_data/` (clips, answer JSONs, CSVs). If an answer looks wrong, ASK.
- Never edit `docs/` or `PLAN.md`. If a spec is wrong or impossible, STOP and report. (Exception: append to `docs/DECISIONS.md`, see section 6.)
- Do not swap the detector, tracker, database or frontend framework.
- Do not run `git commit` or `git tag`.
- Do not write outside the repo or the configured `data/` directory. Never upload footage, crops or datasets anywhere. All labelling and training stays local.
- Face recognition, person re-identification, gait or any biometric matching stay OFF and unbuilt.

## 5. Scope control
Build only what `PLAN.md` asks for. Out of scope unless the human adds it to `PLAN.md`: see `docs/01_PRODUCT_SPEC.md` section 7. If you notice a useful idea, append it to `IDEAS.md` and continue with the plan.

## 6. Decisions and unknowns
- Ambiguous requirement: pick the simplest option consistent with `docs/`, append it to `docs/DECISIONS.md` (date, decision, reason, alternative), and mention it in the step report.
- Any library, package name, CLI flag, model name or API that may have changed: **verify against the installed version** (`pip show`, `--help`, official docs) before relying on memory. Record what you verified.
- Never fabricate benchmark numbers, accuracy figures, dataset results or test outcomes. Unknown means unknown. Every number in a report must come from a script in this repo.

## 6b. Honesty rules for the two headline features (these override convenience)
- **Unknown is a valid state.** Attributes have a state `known` or `unknown`. A rule condition on an `unknown` attribute NEVER matches. Never turn "could not tell" into a positive result or an alert.
- **Worst failures:** (1) a wrong plate silently accepted; (2) a person wrongly flagged as "no ID". When unsure, the plate goes to the review queue and the person stays `unknown`. Never loosen a threshold to make numbers look better; loosening needs measured evidence in `docs/results/`.
- Alerts say what the system saw ("person without visible ID"), never what it cannot know ("student").

## 7. Environment facts
Windows 11 + PowerShell, venv at `.venv` (Python 3.11; 3.10 to 3.12 acceptable), NVIDIA RTX 4070 Ti (12 GB) with CUDA PyTorch, 16 GB RAM, FFmpeg on PATH, MediaMTX started by the human (`C:\mediamtx\mediamtx.exe`; RTSP 8554, WebRTC 8889, HLS 8888), Node LTS. Demo cameras `cam01..cam03` are usually looping files pushed to `rtsp://localhost:8554/cam01..03`. Commands run from `backend/` or `frontend/`.
Code stays cross-platform: `pathlib`, no hard-coded drive letters or separators, no shell-specific code in Python, no symlinks. External binaries (`ffmpeg`, `ffprobe`) paths come from config.
GPU: never silently fall back to CPU in production: log a WARNING. CPU fallback is allowed so tests run anywhere (`device: cpu`).

## 8. Coding standards
- Python 3.11, type hints everywhere, `ruff` clean, docstrings on public classes and functions. Each module docstring says WHY it exists and what to do if it fails (alternatives). Comment non-obvious CV logic (coordinate spaces, thresholds). No wildcard imports, no `print` in app code (use `logging` with camera_id, rule_id, event_id context).
- Config in `config/*.yaml` loaded by `app/config.py` (pydantic-settings, validated). **No magic numbers in code**: every threshold comes from config with a documented default. Secrets only from environment or `.env`.
- Pure-logic packages (`rules/`, `attributes/`, `matching/`) take timestamps as parameters. They never call `time.time()`, never touch the DB, network or disk. Use `core/clock.py` elsewhere.
- Time: UTC integer epoch milliseconds in the DB and API. The UI converts to local time (`Asia/Kolkata`, configurable).
- Concurrency: never block the asyncio loop. Every thread has a name, a stop event, and is joined on shutdown. Every queue is bounded; when full drop the oldest and increment a counter.
- Every external call (RTSP, FFmpeg, MediaMTX, disk, DB) has a timeout and a defined failure behaviour. Never swallow exceptions silently. One camera or worker failing never stops the others.
- Each module that can fail at runtime reports to `core/health.py`.
- Provide small CLI tools under `backend/app/tools/` where PLAN asks, so the human can verify with one command.
- Frontend: TypeScript strict, React + Vite + Tailwind, dark theme, severity colours everywhere: low = blue, medium = amber, critical = red.

## 9. Testing standards
`pytest` (backend), `vitest` (frontend), Playwright (smoke). Tests needing FFmpeg/MediaMTX/GPU/weights carry markers `integration` / `gpu` and skip with a clear reason. Plain `pytest -q` must pass on a machine with no GPU, no MediaMTX and no weights. Prefer deterministic tests: scripted detectors, synthetic tracks, `SimulatedClock`, generated videos (`docs/09_TESTING.md`). Run the WHOLE suite before marking a step passed.

## 10. Performance and safety budgets (never regress silently)
- Analysis at least 8 FPS per camera with 3 cameras on the reference GPU (measure; report honestly if not met).
- Event to alert p95 under 2 s (clip replay). Live view path never depends on analysis (no AI in the live path, never burn boxes into video).
- Plate detection/OCR and torso crops are taken from the **full-resolution** frame, never from the downscaled analysis frame.
- Never delete a clip that is pinned or whose event/review item is still open. Never delete files outside configured data directories.
- Plate text is personal data: never log it above DEBUG. Owner names are hidden from the In-charge role. Every clip view, export and delete is audited.

## 11. Step report (append to PROGRESS.md at the end of every step)
1. What was built (plain English, max 5 lines)  2. Files added/changed  3. Real test output  4. Exact commands for the human to run and check  5. Decisions, deviations, limitations  6. The human checkpoint (copy from PLAN.md).

## 12. If you are stuck or uncertain
Stop. Write the question with the two best options and your recommendation, and ask the human. Asking is always acceptable. Guessing silently is not.
