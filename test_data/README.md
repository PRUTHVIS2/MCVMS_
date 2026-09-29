# test_data

Human-supplied recordings, labels and answers. **The agent never edits anything here.** Videos are gitignored (`*.mp4`); text files are committed.
- `events/`: rule-engine answer files (templates included, fill the `null`s).
- `vehicles/`: plate/vehicle ground truth for the plate baseline (step 11) and identity tests (step 14).
- `id/`: ID-card labels (step 17).
Record with a fixed camera (a phone on a tripod streamed through your RTSP app is fine), 1080p, 30 to 90 s per clip, and note the real clock time of each clip. Film only people who agreed to it.
