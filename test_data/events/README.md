# test_data/events: answer files for the rule engine

Each `*.mp4` you record needs a same-named `*.json` (templates are provided with `null` where you must fill in the truth). `python -m app.tools.run_rules --clip X.mp4 --answer X.json` builds the zones and rules from the JSON, runs the clip in batch mode and compares.

Fields:
- `clip`, `camera`, `source_start` (ISO time with offset; sets the clip's clock so schedules work), `description`.
- `zones`: name, `kind` (`normal` | `special`), `shape` (`polygon` | `line`), `points` normalised 0..1 as `[[x,y],...]` (use the wizard's export, or estimate from a frame), `direction` for lines.
- `rules`: full registered-action specs (see docs/04 s5). A rule refers to the zone by the order it appears (first rule -> first special zone) unless a `zone` name key is added.
- `expected_events`: one entry per event you expect: `rule` (name), `start_s` (seconds from clip start), `end_s` (optional).
- `tolerance_s`: allowed error on start time (default 2 s).
- `expected_events: []` means the clip must produce **no** events.
Rules of the game: the agent never edits these files. If you think an answer is wrong, tell the agent and decide together.

Recording tips: 30 to 90 s per clip, fixed camera, 1080p, note the real clock time for `source_start`. Include consenting people only. Sample scenarios are named after the files here.
