# IDEAS.md (parking lot)
The agent appends ideas here instead of building them. Nothing here is built unless the human adds it to PLAN.md.

## Parked (decided out of scope for now)
- Person re-identification (OSNet), face recognition, repeat-offender tracking for ID cards. Biometric; needs department approval.
- Student vs staff classification. Only feasible with colour-coded lanyards or a registry; ask the department first.
- Fine-grained vehicle make/model recognition (needs an Indian-vehicle dataset). `body_type` (hatchback/sedan/SUV) is the only optional soft attribute, off by default.
- Vehicle appearance re-ID beyond "suggest candidates" (auto-merge without a plate).
- Unresolved-vehicle clusters and "unregistered vehicle seen N times" alerts (design exists in the earlier plate pack: partial-plate patterns + union-find).
- Camera adjacency graph, next-camera prediction, "expected but missing" alerts.
- Open-vocabulary detectors (YOLO-World, Grounding DINO) for new rule subjects without training.
- Overlay-OCR time source for recorded NVR footage (burned-in timestamp).
- Email / Telegram / SMS alert channels (interface stub only).
- Face blur in stored snapshots and thumbnails for the In-charge role.
- Batched multi-camera GPU inference (only if the benchmark step shows the latency target is missed).
- Extra triggers: wrong direction, unattended object, tailgating, AND/OR/NOT and sequence rules.
- Barrier/gate actuator control; automatic fines. Never: a human always decides.

## Add new ideas below
(none yet)
