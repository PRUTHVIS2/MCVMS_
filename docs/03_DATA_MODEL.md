# 03_DATA_MODEL.md

SQLite, WAL mode, `PRAGMA foreign_keys=ON`, `busy_timeout=5000`. Times are integer UTC epoch milliseconds. IDs are TEXT ULIDs unless stated. Migrations are numbered SQL files applied in order with a `schema_version` table. **Enforce invariants in the database where possible** (CHECK constraints and triggers), not only in code.

```sql
CREATE TABLE users(
  id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('owner','admin','incharge')),
  active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
CREATE TABLE user_cameras(user_id TEXT NOT NULL REFERENCES users(id), camera_id TEXT NOT NULL REFERENCES cameras(id),
  PRIMARY KEY(user_id,camera_id));   -- empty for an incharge = all cameras

CREATE TABLE cameras(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, rtsp_url_enc TEXT NOT NULL,   -- Fernet encrypted, never returned by the API
  enabled INTEGER NOT NULL DEFAULT 1,
  features_json TEXT NOT NULL DEFAULT '{"vehicles":true,"id_check":false}',
  width INTEGER, height INTEGER, fps REAL, status TEXT NOT NULL DEFAULT 'unknown', created_at INTEGER NOT NULL);

CREATE TABLE zones(
  id TEXT PRIMARY KEY, camera_id TEXT NOT NULL REFERENCES cameras(id),
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('normal','special')),
  shape TEXT NOT NULL CHECK(shape IN ('polygon','line')),
  points_json TEXT NOT NULL,                 -- normalised [[x,y],...]; line has exactly 2 points
  direction TEXT CHECK(direction IN ('in','out','both')),   -- lines only; 'in' = negative-to-positive side of point1->point2
  is_read_area INTEGER NOT NULL DEFAULT 0,   -- normal polygons: plate reads are attempted here (if none, whole frame)
  enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);

CREATE TABLE registered_actions(
  id TEXT PRIMARY KEY, zone_id TEXT NOT NULL REFERENCES zones(id), name TEXT NOT NULL,
  spec_json TEXT NOT NULL,                   -- validated rule JSON, docs/04_ZONES_AND_RULES.md section 5
  severity TEXT NOT NULL CHECK(severity IN ('low','medium','critical')),
  enabled INTEGER NOT NULL DEFAULT 1, valid_from INTEGER, valid_until INTEGER,
  created_by TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
-- INVARIANT: an action may only reference a zone whose kind = 'special'.
CREATE TRIGGER ra_special_only_ins BEFORE INSERT ON registered_actions
 WHEN (SELECT kind FROM zones WHERE id = NEW.zone_id) <> 'special'
 BEGIN SELECT RAISE(ABORT,'registered actions require a special zone'); END;
CREATE TRIGGER ra_special_only_upd BEFORE UPDATE OF zone_id ON registered_actions
 WHEN (SELECT kind FROM zones WHERE id = NEW.zone_id) <> 'special'
 BEGIN SELECT RAISE(ABORT,'registered actions require a special zone'); END;
-- A special zone that has actions cannot be turned into a normal zone:
CREATE TRIGGER zone_no_downgrade BEFORE UPDATE OF kind ON zones
 WHEN NEW.kind='normal' AND EXISTS(SELECT 1 FROM registered_actions WHERE zone_id=OLD.id)
 BEGIN SELECT RAISE(ABORT,'zone still has registered actions'); END;

CREATE TABLE calendar_exemptions(   -- special cases: holidays, events, exam days
  id TEXT PRIMARY KEY, label TEXT NOT NULL, date_from TEXT NOT NULL, date_to TEXT NOT NULL,   -- local dates YYYY-MM-DD inclusive
  scope TEXT NOT NULL DEFAULT 'all', action_id TEXT REFERENCES registered_actions(id), camera_id TEXT REFERENCES cameras(id),
  created_by TEXT, created_at INTEGER NOT NULL);

CREATE TABLE events(                -- a registered action fired
  id TEXT PRIMARY KEY, action_id TEXT REFERENCES registered_actions(id), zone_id TEXT, camera_id TEXT NOT NULL,
  severity TEXT NOT NULL, kind TEXT NOT NULL,            -- template name or 'system'
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','acknowledged','false_alarm','resolved')),
  started_at INTEGER NOT NULL, ended_at INTEGER, track_id INTEGER,
  subject_json TEXT NOT NULL,       -- attribute snapshot at trigger: {"category":"truck","heavy":true,"plate":"KA05AB1234",...}
  confidence REAL, evidence_json TEXT,     -- n_of_m, frames, box, snapshot path
  vehicle_id INTEGER REFERENCES vehicles(id), sighting_id TEXT REFERENCES sightings(id),
  id_check_id TEXT REFERENCES id_checks(id),
  clip_id TEXT REFERENCES clips(id), escalated_from TEXT, dry_run INTEGER NOT NULL DEFAULT 0,
  ack_by TEXT, ack_at INTEGER, note TEXT);
CREATE INDEX ix_events_time ON events(started_at); CREATE INDEX ix_events_action ON events(action_id, started_at);

CREATE TABLE clips(
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('event','sighting')), camera_id TEXT NOT NULL,
  path TEXT, sidecar_path TEXT, start_ts INTEGER, end_ts INTEGER, duration_s REAL, size_bytes INTEGER, sha256 TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','ready','needs_repair','incomplete','failed','expired')),
  protected INTEGER NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0,
  retention_class TEXT, expires_at INTEGER, created_at INTEGER NOT NULL);

CREATE TABLE alerts(
  id TEXT PRIMARY KEY, level TEXT NOT NULL CHECK(level IN ('low','medium','critical')), kind TEXT NOT NULL,
  message TEXT NOT NULL, target_type TEXT, target_id TEXT, event_id TEXT REFERENCES events(id),
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','acknowledged','dismissed','expired')),
  created_at INTEGER NOT NULL, expires_at INTEGER, ack_by TEXT, ack_at INTEGER, dismiss_reason TEXT, count INTEGER NOT NULL DEFAULT 1);

-- Vehicles (persistent identity) ---------------------------------------
CREATE TABLE registry_entries(     -- imported/managed list of known vehicles
  id TEXT PRIMARY KEY, plate TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('staff','student','visitor','service','other')),
  category TEXT, colour TEXT, owner_label TEXT,       -- owner_label hidden from incharge
  valid_from TEXT, valid_until TEXT, active INTEGER NOT NULL DEFAULT 1, note TEXT, created_at INTEGER NOT NULL);
CREATE UNIQUE INDEX ux_registry_plate ON registry_entries(plate) WHERE active=1;

CREATE TABLE vehicles(
  id INTEGER PRIMARY KEY AUTOINCREMENT,             -- shown as V-000123
  plate TEXT UNIQUE,                                -- normalised; NULL for tentative appearance-only identities (not created by default)
  plate_source TEXT CHECK(plate_source IN ('auto','admin','registry')),
  category TEXT, colour TEXT, body_type TEXT,
  registry_id TEXT REFERENCES registry_entries(id),
  label TEXT, notes TEXT, pinned INTEGER NOT NULL DEFAULT 0,
  first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL, sightings_count INTEGER NOT NULL DEFAULT 0,
  merged_into INTEGER REFERENCES vehicles(id));

CREATE TABLE sightings(
  id TEXT PRIMARY KEY, camera_id TEXT NOT NULL REFERENCES cameras(id), track_id INTEGER NOT NULL,
  source TEXT NOT NULL CHECK(source IN ('live','batch')),
  first_ts INTEGER NOT NULL, last_ts INTEGER NOT NULL,
  category TEXT, category_conf REAL, heavy INTEGER, colour TEXT, colour_conf REAL, body_type TEXT,
  plate_final TEXT, plate_conf REAL, plate_partial TEXT, plate_source TEXT CHECK(plate_source IN ('auto','admin')),
  status TEXT NOT NULL CHECK(status IN ('pending','resolved','verify','unregistered','needs_review','confirmed','dismissed')),
  match_type TEXT, review_reason TEXT,
  vehicle_id INTEGER REFERENCES vehicles(id), link_type TEXT CHECK(link_type IN ('plate','admin','appearance','none')),
  candidates_json TEXT,                              -- top-3 registry/vehicle candidates or appearance candidates
  zones_json TEXT NOT NULL DEFAULT '[]',             -- [{zone_id,enter_ts,exit_ts}] normal AND special zones
  best_crop_path TEXT, plate_crop_path TEXT, clip_id TEXT REFERENCES clips(id),
  flags_json TEXT NOT NULL DEFAULT '{}', stamps_json TEXT, created_at INTEGER NOT NULL);
CREATE INDEX ix_sightings_vehicle ON sightings(vehicle_id, first_ts);
CREATE INDEX ix_sightings_time ON sightings(first_ts);
CREATE INDEX ix_sightings_status ON sightings(status);
CREATE VIRTUAL TABLE sightings_fts USING fts5(sighting_id UNINDEXED, plate, tokenize='trigram');  -- partial plate search; verify FTS5 trigram support at step 0

CREATE TABLE plate_reads(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sighting_id TEXT NOT NULL REFERENCES sightings(id) ON DELETE CASCADE,
  ts INTEGER NOT NULL, text TEXT, conf REAL, char_confs_json TEXT, engine TEXT, preprocess TEXT,
  plate_w_px INTEGER, sharpness REAL, crop_path TEXT);

CREATE TABLE vehicle_embeddings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id INTEGER REFERENCES vehicles(id), sighting_id TEXT REFERENCES sightings(id) ON DELETE CASCADE,
  camera_id TEXT, ts INTEGER, model TEXT, dim INTEGER, vec BLOB NOT NULL);   -- float32, L2-normalised

CREATE TABLE review_items(
  id TEXT PRIMARY KEY, sighting_id TEXT UNIQUE NOT NULL REFERENCES sightings(id),
  reason TEXT NOT NULL CHECK(reason IN ('no_plate','low_confidence','ambiguous','invalid_format','appearance_candidate','spot_check')),
  priority INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved','dismissed')),
  due_at INTEGER, created_at INTEGER NOT NULL, resolved_at INTEGER, resolved_by TEXT, resolution TEXT);

CREATE TABLE training_samples(     -- plate crops with confirmed text (docs/05 section 9)
  id INTEGER PRIMARY KEY AUTOINCREMENT, sighting_id TEXT, crop_path TEXT NOT NULL, label TEXT NOT NULL,
  split TEXT NOT NULL CHECK(split IN ('train','val','test')), created_at INTEGER NOT NULL);

-- ID-card checks --------------------------------------------------------
CREATE TABLE id_checks(            -- one row per person track that was evaluated
  id TEXT PRIMARY KEY, camera_id TEXT NOT NULL REFERENCES cameras(id), track_id INTEGER NOT NULL,
  first_ts INTEGER NOT NULL, last_ts INTEGER NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('wearing','not_wearing','unknown')),
  good_frames INTEGER NOT NULL, p_wear_max REAL, p_no_id_mean REAL, reason TEXT,
  evidence_dir TEXT,               -- up to N torso crops + 1 snapshot; short retention
  feedback TEXT CHECK(feedback IN ('confirmed','false_alarm')), feedback_by TEXT, feedback_at INTEGER, created_at INTEGER NOT NULL);

CREATE TABLE audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, user_id TEXT, action TEXT NOT NULL, target TEXT, detail_json TEXT);
CREATE TABLE settings(key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
CREATE TABLE schema_version(version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL);
```

## Notes
- `events.subject_json` stores the attribute snapshot so history stays meaningful even if the vehicle is later merged or its plate corrected.
- `sightings.status`: `pending` (track still running) -> `resolved` | `verify` | `unregistered` | `needs_review` (from the finalizer) -> `confirmed`/`dismissed` (admin). Meaning of each in `docs/05_VEHICLES.md` section 4.
- Merging vehicles sets `merged_into`; queries follow the pointer. Splitting moves selected sightings to a new vehicle. Both are audited and reversible for 30 days (`audit_log` holds the inverse).
- Owner names (`registry_entries.owner_label`) are stripped from every response model for the `incharge` role. A test checks every response model.
- Retention deletes clips and evidence, not `vehicles` / `sightings` metadata (kept `metadata_days`, `docs/07_STORAGE.md`).
- Each clip has a sidecar JSON next to it (`meta.json`) with enough to rebuild the row.
