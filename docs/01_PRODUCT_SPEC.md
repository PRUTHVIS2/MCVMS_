# 01_PRODUCT_SPEC.md

## 1. Purpose
A college project (MCA internship, Team 18) that turns ordinary IP cameras into a system that (A) understands vehicles and (B) notices people without a visible ID card, using one shared idea: **the admin draws zones on camera footage and attaches registered actions (rules) to them.**

### A. Vehicle intelligence
- Detect vehicles on every vehicle-enabled camera. For each vehicle sighting record **type, colour, number plate** and metadata (camera, zones visited, times, confidence, best crop) into a **persistent store**.
- The same vehicle seen by different cameras, on different days, is stored under **one tag** (`V-000123`). The plate is the authoritative key. Appearance only suggests candidates for a human to confirm.
- Every sighting produces one **10 s clip**.
- Optional soft attribute `body_type` (hatchback/sedan/SUV/...) exists behind a switch, default OFF. Fine-grained make/model recognition is NOT built.
- Registered actions on special zones can use vehicle attributes, for example: "a heavy truck must not be seen in this zone between 09:00 and 17:00; if seen, raise a critical alert."

### B. No ID card
- An admin draws a zone (for example the college entrance walkway), saves it, and registers the action "person without visible ID card".
- The system alerts only when it is confident a person is **not wearing a visible ID card**. When it cannot tell (back turned, card hidden, too small) the state is `unknown` and nothing fires.
- Admins choose what is watched, when the rule is armed, how long the condition must hold, the alert severity and escalation, and special cases (exempt dates, time windows).

### Shared
Zones (normal vs special), registered actions, alerts, event clips with pre-roll, review queue, dashboard, roles, audit.

## 2. Vocabulary
| Term | Meaning |
|---|---|
| Camera | An RTSP source (or a file in batch mode). Has `features`: `vehicles`, `id_check`. |
| Zone | A polygon or a line the admin draws on a camera view. Has `kind`: `normal` or `special`. |
| Normal zone | A named area. Nothing is registered on it, but every sighting records which normal zones it visited (searchable), and it can act as the plate "read area". **Registered actions are not allowed.** |
| Special zone | A zone on which the admin may register actions. Enforced by the API and the database, not only the UI. |
| Registered action (rule) | "In this special zone, when a subject matching these conditions does this for this long, during this schedule, do that response." Table `registered_actions`. |
| Subject | What a rule watches: a `vehicle` or a `person`, plus attribute conditions. |
| Attribute | A fact about a track with a confidence and a state `known`/`unknown` (for example `category=truck`, `id_state=not_wearing`). |
| Track | One object followed over time in one camera (ByteTrack id). |
| Sighting | One vehicle track finalised into a database record with attributes, clip and identity link. |
| Vehicle (tag) | The persistent identity `V-000123` that groups sightings across cameras and days. |
| Event | A rule fired (with evidence, clip, severity). |
| Alert | The notification for an event or a system condition. Levels: low, medium, critical. |
| Review item | Something the AI could not decide (plate unread, ambiguous). A human resolves it. |

## 3. Users and roles
| Role | Can |
|---|---|
| Owner | Everything, including users, retention, wiping data. Created from `.env` on first start. |
| Admin | Cameras, zones, rules, registry, review queue, dismiss alerts, see owner names. |
| In-charge | View live, events, vehicles (plates but **not owner names**), acknowledge alerts, work the review queue. Cannot edit cameras/zones/rules. Optionally limited to assigned cameras. |
Full permission matrix in `docs/08_API_AND_UI.md`.

## 4. Phases and milestones
| Phase | Steps | Milestone demo |
|---|---|---|
| A. Foundation | 0 to 10 | Draw a special zone on a demo camera, register "heavy vehicle (truck/bus) in this zone in a time window", play a clip with a truck, get a critical alert with clip and pre-roll. Normal zones cannot take rules. |
| B. Vehicles | 11 to 16 | Drive vehicles past two cameras. Vehicles page shows one tag per plate with a timeline of sightings and 10 s clips; unreadable ones land in the review queue; a rule on "unregistered vehicle in this zone" fires. |
| C. ID card | 17 to 19 | Play the entrance clip: people without a visible ID get low alerts, five in ten minutes escalate to medium, people wearing a card or with unclear view get nothing. |
| D. Finish | 20 to 21 | Benchmarks, retention, hardening, demo script, results report. |

## 5. Targets (goals to MEASURE and report honestly, not claims)
| Area | Goal | How measured |
|---|---|---|
| Analysis speed | 8 FPS per camera with 3 cameras | `tools/bench` |
| Event to alert (clip replay) | p95 under 2 s | `tools/bench` |
| Rule engine | Zero mismatches against test answer JSONs (`test_data/events`) | `tools/run_rules` |
| Plate exact read, good daylight view | 80 percent or more | `scripts/plate_baseline.py` |
| Wrong-accepted plates (status resolved but wrong) | 1 percent or less | same |
| Review load | 25 percent or less of sightings | same |
| ID: false accusation (wearing person marked not_wearing) | 5 percent or less of wearing tracks | `scripts/id_baseline.py` |
| ID: not_wearing precision on good-view tracks | 85 percent or more | same |
| ID: unknown rate | reported, no target | same |
If a goal is missed, report the number and propose a fix. Do not tune thresholds without evidence.

## 6. Honest limitations (shown to the user in the UI "About accuracy" page)
- Plates: unreadable at night glare, extreme angles, dirty or damaged plates. Many two-wheelers carry no readable front plate, so bikes need a rear-facing view.
- Colour is unreliable at night and under coloured lighting. Silver, grey and white are easily confused. Colour is never used for identity.
- "Heavy" is a heuristic from the detected category (truck, bus). Small trucks and tempos may be classed as trucks; auto-rickshaws need a custom class.
- ID card: a small object. It works only when people face the camera at a distance where the torso is large enough (`tools/id_probe` tells you). A hidden or flipped card looks like "no card"; the system therefore requires several good frames and otherwise says `unknown`.
- The system cannot know a person is a student. It reports "person without visible ID" and a human verifies.
- Appearance-based vehicle matching is only a suggestion, never an automatic merge.

## 7. Out of scope (do not build, do not add dependencies for)
Face recognition or any biometric matching, person re-identification, staff/student classification, make/model recognition, licence-plate lookup against external government databases, audio recording, cloud upload, mobile apps, actuator/barrier control, automatic penalties, multi-site federation, email/SMS/Telegram delivery (interface stub only).

## 8. Privacy and compliance (placeholders the department must fill)
Footage of students and vehicle owners is personal data (India: DPDP Act 2023). Before any recording of real people: written approval from the department, signage, defined retention (`config/storage_policy.yaml`), access policy, and consent from every person filmed for test data. The system: no audio, role-limited access, audited views/exports, short retention for ID-card evidence, plate text never logged above DEBUG, owner names hidden from In-charge. Face matching stays disabled.

## 9. Assumptions to confirm (log answers in `docs/DECISIONS.md`)
1. Where cameras are mounted and their resolution (drives whether plates/IDs are readable). 2. Whether RVCE ID cards hang on lanyards of a known colour. 3. Source and format of a vehicle registry, if one exists. 4. Retention limits. 5. Who receives alerts and what "special cases" the department wants.
