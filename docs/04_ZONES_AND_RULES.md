# 04_ZONES_AND_RULES.md

The rule engine is the heart of both features. It lives in `app/rules/` and is **pure**: no clocks, DB, network, disk. It consumes tracks with attributes and time, and emits decisions. Attribute *resolvers* (plates, colour, ID card) are separate (`docs/05`, `docs/06`); the engine only reads their results.

## 1. Zones
- **Shapes:** `polygon` (3 to 20 points, simple non-self-intersecting, validated) or `line` (2 points, plus `direction`). Stored normalised, converted to full-res pixels per stream size.
- **Kinds:**
  - `normal`: named area. No registered actions allowed (DB trigger + API 422 + UI hides the option). Used for (a) the "zones visited" history on every sighting, (b) an optional **read area** (`is_read_area=1`): plate reading is attempted only there; with no read area the whole frame is used.
  - `special`: may hold registered actions. Also records zones visited.
- Changing a zone's shape while actions exist is allowed but the API returns a warning and the wizard asks to re-run the dry run. Deleting a zone with actions requires explicit confirmation and deletes the actions (audited).
- **Test point for a polygon:** the **foot point** = bottom-centre of the box for vehicles and persons. A vehicle is "in" a zone when its foot point is inside. (Configurable `rules.test_point: foot|centre`.) Standard point-in-polygon with boundary counted inside.
- **Line direction convention** (screen coordinates, y down): for a line from P1 to P2, the side is `sign(cross(P2-P1, X-P1))`. `in` means the foot point moves from the negative side to the positive side; `out` the reverse. The wizard draws an arrow to the "in" side and the admin can flip it.

## 2. Attribute catalogue (the only fields a rule may reference)
Every attribute has `state: known|unknown` and a confidence. **`unknown` never matches any condition.**

| Subject | Attribute | Values | Produced by |
|---|---|---|---|
| vehicle | `category` | `two_wheeler`, `auto_rickshaw`, `car`, `bus`, `truck` | detector class vote (docs/05 s2) |
| vehicle | `heavy` | `true`/`false` (from `heavy_categories` in config) | derived from `category` |
| vehicle | `colour` | `black`, `white`, `grey_silver`, `red`, `orange_yellow`, `green`, `blue`, `brown` | HSV (docs/05 s2), unknown at night |
| vehicle | `body_type` | `hatchback`, `sedan`, `suv`, `van`, `pickup` (only if enabled) | optional zero-shot classifier |
| vehicle | `plate` | normalised text; ops `eq`, `in`, `startswith` | plate pipeline (provisional live, final at sighting end) |
| vehicle | `registry_status` | `registered`, `unregistered` | matcher (needs a plate result) |
| vehicle | `registry_kind` | `staff`, `student`, `visitor`, `service`, `other` | registry |
| vehicle | `vehicle_id` | integer id | identity linking |
| person | `id_state` | `wearing`, `not_wearing` (`unknown` = state, not a value) | ID resolver (docs/06) |

Condition JSON: `{"attr":"category","op":"in","value":["truck","bus"]}`. Ops: `eq`, `ne`, `in`, `not_in`, `startswith` (strings). Conditions in `where` are ANDed. Because unknown never matches, a rule "unregistered vehicles" fires only once the plate has been read well enough to decide `unregistered` (never on "could not read").

**Late binding.** Attributes improve over time (a plate may resolve seconds after the vehicle enters). The evaluator re-evaluates conditions every tick, so a rule fires when its conditions first become true while the object is in the zone. The event's `subject_json` is completed later (`event.updated`) when more attributes resolve (for example the plate of the heavy truck).

## 3. Confirmation and stability (all pure, all config)
Per (rule, track) the engine keeps a rolling window of the last `M` ticks of "condition holds" booleans (`confirm.n_of_m`, default 4 of 5). Fire only when: N of M true, the mean detection confidence of the subject over those ticks is at least `confirm.min_confidence`, and the object's box height is at least `subject.min_box_px` (if set). Hysteresis: after firing, the condition counts as "still active" until confidence drops below `min_confidence - hysteresis_drop`. Track loss shorter than `track_loss_tolerance_s` (1.5) does not end an event.

## 4. Templates (trigger types)
| Template | Fires when | Params |
|---|---|---|
| `presence` | condition holds continuously (per confirmation) for `min_seconds` while the subject is in the zone (polygon) | `min_seconds` (0 = immediately after confirmation) |
| `dwell` | subject stays in the zone longer than `dwell_seconds` (timer restarts after `reset_after_s` outside) | `dwell_seconds`, `reset_after_s` |
| `line_crossing` | foot point crosses the line in the configured direction with the subject conditions true at the crossing tick | none (direction on the zone) |
| `count_threshold` | at least `count` distinct tracks matching the subject conditions are in the zone at the same time for `min_seconds` | `count`, `min_seconds` |
Template applicability: `line_crossing` needs a line zone, others need a polygon. A rule never mixes subject kinds.

**The two headline rules are presets of these templates:**
- *Heavy vehicle in zone:* `subject={kind:vehicle, where:[{attr:heavy,op:eq,value:true}]}`, `trigger={template:presence, min_seconds:2}`, `schedule` = the forbidden hours.
- *No ID card:* `subject={kind:person, where:[{attr:id_state,op:eq,value:not_wearing}], min_box_px:150}`, `trigger={template:presence, min_seconds:1}`, severity low, escalation by count.

## 5. Registered action JSON (validated by pydantic, stored in `registered_actions.spec_json`)
```json
{
  "name": "No heavy vehicles during college hours",
  "subject": {"kind": "vehicle", "where": [{"attr": "heavy", "op": "eq", "value": true}], "min_box_px": 80},
  "trigger": {"template": "presence", "min_seconds": 2},
  "confirm": {"n_of_m": [4, 5], "min_confidence": 0.6},
  "schedule": {"days": ["mon","tue","wed","thu","fri","sat"], "from": "09:00", "to": "17:00", "timezone": "Asia/Kolkata"},
  "valid": {"from_date": "2026-10-01", "until_date": null},
  "exemptions": {"calendar_ids": [], "note": ""},
  "response": {
    "severity": "critical",
    "pre_roll_s": 15, "hold_s": 20, "max_clip_min": 15,
    "cooldown_s": 300,
    "alert_ttl_min": 240,
    "escalation": []
  }
}
```
Field meanings (the wizard uses these words):
- **schedule** = when the rule is *armed* each day (times may cross midnight, `from` > `to`). Omit for always armed. Evaluated in local time using the object's timestamp.
- **valid** = how long the rule is *active in calendar terms* (`from_date`..`until_date` inclusive, local dates). Outside it the rule is inert.
- **exemptions.calendar_ids** = special-case dates from `calendar_exemptions` (holidays, exam days, events). `scope` on an exemption can be all rules, one rule, or one camera.
- **trigger.min_seconds** = how long the condition must hold before firing.
- **cooldown_s** = after an event for the same (rule, track) or (rule, vehicle_id) ends, do not fire again for this long.
- **alert_ttl_min** = an unacknowledged alert auto-expires (status `expired`) after this long.
- **escalation** = list of `{"if_count_in_window": {"n": 5, "window_min": 10}, "severity": "medium"}` evaluated over *this rule's recent events*; the highest matching severity wins and the event/alert says `escalated`. Pure function `escalation.pick_severity(base, escalation, recent_event_times, now)`.
- **response.severity** low | medium | critical; alert wording in `docs/08`.
Defaults for missing optional fields come from `config/app.yaml -> rules`.

## 6. Engine interface
```python
class RuleEngine:
    def __init__(self, rules: list[CompiledRule], zones: dict[str, CompiledZone], cfg: RulesConfig): ...
    def step(self, frame: TrackedFrame, attrs: dict[int, TrackAttributes], now_ms: int,
             exempt: Callable[[str, int], bool]) -> list[Decision]
    def flush(self, now_ms: int) -> list[Decision]   # end of stream: close open events
# Decision: kind = 'start' | 'update' | 'end', rule_id, track_id, ts_ms, subject_snapshot, confidence, evidence
```
Deterministic: identical input gives identical decisions. State is per (rule, track). The engine never reads a clock and never sleeps.

## 7. Dry run and answer files
- `python -m app.tools.run_rules --clip test_data/events/x.mp4 --answer test_data/events/x.json` runs batch analysis and compares decisions with the answer file (start time within `tolerance_s`, correct rule, expected count). Prints PASS/FAIL per clip with a diff.
- The wizard's **dry run** runs a chosen rule over a chosen stored clip and shows what would have fired, marked `dry_run=1` (never alerts, never saved as real events unless the admin asks to keep the example).
- Answer file format: `test_data/events/README.md`.

## 8. Required tests (pure, no GPU)
Point-in-polygon and boundary; line crossing directions incl. flip and jitter; presence with flicker (N of M) and track loss tolerance; dwell reset; count threshold; schedule across midnight and day filters; valid dates; calendar exemption; cooldown; escalation windows; **unknown attribute never matches**; late-binding attribute fires when it turns known; `normal` zone rejected for actions at API and DB layers (trigger test with raw SQL); template/shape mismatch rejected; determinism (same input twice gives same output); no `time.time` in `rules/` (grep test).
