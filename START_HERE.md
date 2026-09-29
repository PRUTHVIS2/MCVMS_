# START_HERE.md (for you, the human)

## What this pack is
Instructions for an AI coding agent (Antigravity + Gemini/Claude) to build **MCVMS**, step by step, with you approving each step.
- **Feature A:** vehicles: type, colour, plate, persistent tag across cameras and days, 10 s clip per sighting, rules like "no heavy truck in this zone at this time".
- **Feature B:** people without a visible ID card, driven entirely by zones and registered actions, with severity levels and special cases.
- **Zones:** each zone is **normal** (just records) or **special** (may hold registered actions). Enforced in the database, API and UI.
It merges your two earlier packs: the first pack's zones/rules/clips/alerts/dashboard, and the second pack's plate pipeline, registry and review queue. Person re-identification and face recognition were dropped on purpose.

## Files
| File | For |
|---|---|
| `AGENT_RULES.md` | The agent's rulebook (it reads it first every session) |
| `PLAN.md` | 22 gated steps (0 to 21) with tests and your checkpoint per step |
| `PROGRESS.md` | The agent's report card. You fill the checkpoint log |
| `IDEAS.md` | Parking lot for ideas that are not built yet |
| `docs/01..09` | The spec: product, architecture, data model, rules, vehicles, ID card, storage, API/UI, testing |
| `docs/DECISIONS.md` | Decisions and open questions (answer them as you go) |
| `config/` | All thresholds (`app.yaml`) and retention (`storage_policy.yaml`) |
| `test_data/` | Where your recordings, labels and answer files go (agent never edits) |

## Setup once
1. Unzip to a folder, e.g. `C:\dev\mcvms`. Open the folder in Antigravity. Run `git init`, then `git add . && git commit -m "pack"`.
2. Install: Python 3.11, Node LTS, FFmpeg (on PATH), NVIDIA driver + CUDA PyTorch, MediaMTX (`C:\mediamtx\mediamtx.exe`). The agent's step 0 checks all of this.
3. Copy `.env.example` to `.env` and fill in a password, JWT secret and Fernet key (command inside the file).
4. Start MediaMTX in its own terminal.

## How to drive the agent
Start of every new chat/session, paste:
> Read AGENT_RULES.md, PROGRESS.md and PLAN.md. Tell me which step is next and what it depends on. Do not write code yet.

Run a step:
> Do PLAN.md step N.

When it reports "passed":
1. Read its step report in `PROGRESS.md` (real test output pasted).
2. Do the **Human checkpoint** listed for that step in `PLAN.md`. Write the result in the checkpoint log.
3. If good: commit (`git add . && git commit -m "step N"`), then say:
> Step N is approved. Do PLAN.md step N+1.
If not good: describe exactly what you saw. Do not say "it's broken" without the command and output.

If the agent writes `BLOCKED.md`: read it, pick option A or B, and tell it. If it starts building beyond the step, say: "Stop. Only step N. Revert extra work."
If you change your mind about scope: edit `PLAN.md`/`docs` yourself (the agent may not), commit, and tell the agent to re-read them.

## What YOU must supply (and when)
| When | What |
|---|---|
| Step 4 | A few short clips of a truck/bus, cars and bikes crossing an area; fill `test_data/events/*.json` (zones, expected events) |
| Step 6 | A real clip through a zone to watch the alert live |
| Before step 11 | Record at least 100 vehicle passes at the intended camera position; fill `passes_ground_truth.csv`, `registry_test.csv`; plate detector weights at `data/models/plate.pt` |
| Before step 14 | Two camera views of the same vehicles for `cross_camera_pairs.csv` (30 same, 60 different pairs) |
| Before step 17 | Entrance footage with and without ID cards, `id_ground_truth.csv`, sorted torso crops (agent gives tools) |
| Any time | Answers to the open questions in `docs/DECISIONS.md` |
Only film people and vehicles that agreed. Get the department's OK before recording on campus. Keep all data on your machine.

## Milestones (demo checkpoints)
- **A (step 10):** draw a special zone, register the heavy-vehicle rule, truck clip -> critical alert + clip; normal zone refuses rules.
- **B (step 16):** vehicles across two cameras -> one tag, 10 s clips, review queue, unregistered-vehicle rule.
- **C (step 19):** entrance clip -> alerts for people without visible ID; wearers and unclear views ignored.
If time runs short, stop after A + B, or A + C. Both gates (steps 11 and 17) exist so you find out early whether the cameras can support the feature.

## Honest expectations
Plates and ID cards depend on camera position and resolution more than on code. Step 11 and step 17 will tell you the truth with numbers. If a camera cannot read plates or see torsos, move the camera or the zone; the agent will show you how (probe tools). An alert saying "person without visible ID" is a prompt for a human to check, not a verdict.

## Quick answers to "how long should a rule be active?"
In the rule builder: **Schedule** = which days/hours it is armed; **Active dates** = from/until date; **Min seconds** = how long before alerting; **Cooldown** = pause before the same subject can alert again; **Alert expiry** = how long an unacknowledged alert stays open. Special cases = **exemption dates** (holidays, exams, events) and **escalation** ("5 in 10 minutes -> medium").
