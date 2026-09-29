# DECISIONS.md (append-only; agent and human record decisions here)

Format: `YYYY-MM-DD | decision | reason | alternative considered | who`.

## Seeded design decisions (pack authors)
- Single backend process with threads instead of process-per-camera | simpler, models share the GPU, fewer moving parts for a student project | process-per-camera (revisit only if step 20 shows a bottleneck) | pack
- Plate is the authoritative vehicle identity; appearance embeddings only suggest candidates | appearance matching would merge look-alike vehicles | auto-merge by appearance | pack
- Vehicle make/model recognition NOT built; type + colour (+ optional coarse `body_type`, default off) | no Indian-vehicle dataset; low value for the effort | fine-grained classifier | pack
- Person re-identification and face recognition dropped | not required by scope; biometric and privacy-heavy | OSNet Re-ID from the earlier pack | pack
- `id_state` has three states; `unknown` never alerts | absence of a detection is not proof of absence of a card | binary wearing/not wearing | pack
- ID card handled by pose -> torso crop -> classifier -> per-track aggregation, not full-frame small-object detection | a card is only tens of pixels in a wide shot | YOLO detector fine-tune on `id_card` (fallback if Gate 2 fails) | pack
- Special vs normal zone enforced in the DB (triggers), the API (422) and the UI | a UI-only check can be bypassed | UI only | pack
- "Heavy" derived from detector category (truck, bus) | no weight information in video; a custom model can refine | box-size heuristic | pack
- Human commits to git; agent stops after each step | student keeps control and a clean history | agent commits | pack
- "Registered action active for how long" is modelled as: `schedule` (armed hours), `valid` (calendar dates), `trigger.min_seconds` (how long before alerting), `cooldown_s`, `alert_ttl_min` (how long an alert stays open) | the phrase was ambiguous; these cover each reading | single duration field | pack

## Open questions (fill answers before the related step)
- Camera mounting, resolution and angle at the real sites (steps 11, 17)
- RVCE ID card style: lanyard? colour scheme? (step 17; decides whether a lanyard resolver is worth adding)
- Vehicle registry source and format (step 13)
- Retention values and access policy from the department (step 20)
- Who receives alerts (dashboard only for now)

## Log
(none yet)
