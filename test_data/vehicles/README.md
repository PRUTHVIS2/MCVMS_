# test_data/vehicles

- `passes_ground_truth.csv`: one row per vehicle passing a camera in your recordings (at least 100 rows for the plate baseline, step 11).
  Columns: `clip,camera,pass_no,approx_time_s,true_plate,plate_readable,category,colour,view,light,direction,notes`
  - `plate_readable`: `yes` (you can read all characters in the video), `partial`, `no`.
  - `true_plate`: the real plate (from the vehicle or a still photo taken at the time), blank if unknown. For partial rows put the certain characters and `*` for unsure ones in `notes`.
  - `category`: two_wheeler | auto_rickshaw | car | bus | truck. `colour`: black | white | grey_silver | red | orange_yellow | green | blue | brown. `view`: front | rear | side. `light`: day | dusk | night. `direction`: in | out | na.
- `registry_test.csv`: some (not all) of the true plates as registered, plus 2 or 3 decoy plates that differ by one character from real ones. Columns match the registry import: `plate,kind,category,colour,owner_label,valid_from,valid_until,note`. Use fake owner labels.
- `cross_camera_pairs.csv`: `clip_a,pass_a,clip_b,pass_b,same_vehicle` (yes|no), at least 30 yes and 60 no, for the appearance-embedder comparison (step 14).
The example rows in the CSVs are marked and must be deleted. Only film vehicles whose owners agree (friends, family, your own) or public roads with the department's approval. Avoid faces.
