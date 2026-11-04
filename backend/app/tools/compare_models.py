"""Compare detection counts and inference FPS between old and new model weights.

Usage:
    python -m app.tools.compare_models [--max-frames 600] [--batch-size 16]
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import torch
from ultralytics import YOLO

from app.config import config


def get_detector_instance(model_path: str, class_map: dict[int, str]):
    """Instantiate a standalone detector runner for benchmark comparison."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = YOLO(model_path)
    if device == "cuda":
        model.to("cuda")
    return model, class_map, device


def evaluate_video(
    video_path: Path,
    model: YOLO,
    class_map: dict[int, str],
    max_frames: int = 600,
    batch_size: int = 16,
) -> tuple[dict[str, int], float, int]:
    """Run model on video clip and count detections per category."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    counts: dict[str, int] = {cat: 0 for cat in set(class_map.values())}
    # Add auto_rickshaw even if 0
    counts.setdefault("auto_rickshaw", 0)

    total_frames = 0
    t0 = time.time()
    batch_frames = []

    def run_batch(frames):
        if not frames:
            return
        results = model.predict(
            frames,
            imgsz=640,
            verbose=False,
            conf=0.25,
            classes=list(class_map.keys()),
        )
        for r in results:
            if r.boxes is not None:
                for b in r.boxes:
                    cls_id = int(b.cls.item())
                    if cls_id in class_map:
                        cat = class_map[cls_id]
                        counts[cat] = counts.get(cat, 0) + 1

    while True:
        if 0 < max_frames <= total_frames:
            break
        ret, frame = cap.read()
        if not ret:
            break
        batch_frames.append(frame)
        total_frames += 1

        if len(batch_frames) >= batch_size:
            run_batch(batch_frames)
            batch_frames.clear()

    if batch_frames:
        run_batch(batch_frames)
        batch_frames.clear()

    cap.release()
    elapsed = time.time() - t0
    fps = total_frames / elapsed if elapsed > 0 else 0.0
    return counts, fps, total_frames


def main():
    parser = argparse.ArgumentParser(description="Compare detector models")
    parser.add_argument("--old-weights", default="yolo11n.pt", help="Path to old weights")
    parser.add_argument(
        "--new-weights",
        default=config.models.get("vehicle_detector", "data/models/detector_idd_best.pt"),
        help="Path to new weights",
    )
    parser.add_argument("--max-frames", type=int, default=600, help="Max frames per video (0 for all)")
    parser.add_argument("--batch-size", type=int, default=16, help="Inference batch size")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    backend_root = Path(__file__).resolve().parent.parent.parent

    def resolve_file(p_str: str) -> Path:
        p = Path(p_str)
        if p.exists():
            return p
        if (backend_root / p_str).exists():
            return backend_root / p_str
        if (repo_root / p_str).exists():
            return repo_root / p_str
        raise FileNotFoundError(f"Cannot find {p_str}")

    old_weights_path = resolve_file(args.old_weights)
    new_weights_path = resolve_file(args.new_weights)

    # Old model class map: standard COCO
    old_class_map = {
        0: "person",
        2: "car",
        3: "two_wheeler",
        5: "bus",
        7: "truck",
    }

    # New model class map: approved IDD map from config
    new_class_map = {int(k): str(v) for k, v in config.models.get("class_map", {}).items()}
    if not new_class_map:
        new_class_map = {
            0: "person",
            2: "two_wheeler",
            3: "auto_rickshaw",
            4: "car",
            5: "bus",
            6: "truck",
        }

    print(f"Old Model: {old_weights_path} (COCO map: {old_class_map})")
    print(f"New Model: {new_weights_path} (IDD map:  {new_class_map})")

    # Discover videos
    video_paths = []
    for d in ["test_data/events", "test_videos"]:
        dir_path = repo_root / d
        if not dir_path.exists():
            dir_path = backend_root / d
        if dir_path.exists():
            video_paths.extend(sorted(dir_path.glob("*.mp4")))

    if not video_paths:
        print("No videos found to evaluate.")
        sys.exit(1)

    print(f"Found {len(video_paths)} videos:")
    for v in video_paths:
        print(f"  - {v}")

    # Load models
    old_model, _, old_dev = get_detector_instance(str(old_weights_path), old_class_map)
    new_model, _, new_dev = get_detector_instance(str(new_weights_path), new_class_map)
    print(f"Old model running on {old_dev}, New model running on {new_dev}\n")

    categories = ["person", "car", "two_wheeler", "auto_rickshaw", "bus", "truck"]

    results = []

    for vp in video_paths:
        # For test_data/events (short clips), always run full; for test_videos, obey max_frames
        is_short_event = "test_data" in str(vp)
        clip_max_frames = 0 if is_short_event else args.max_frames

        print(f"--> Evaluating {vp.name} (max_frames={clip_max_frames or 'all'})...")

        old_counts, old_fps, old_n = evaluate_video(
            vp, old_model, old_class_map, max_frames=clip_max_frames, batch_size=args.batch_size
        )
        new_counts, new_fps, new_n = evaluate_video(
            vp, new_model, new_class_map, max_frames=clip_max_frames, batch_size=args.batch_size
        )

        results.append({
            "clip": vp.name,
            "folder": vp.parent.name,
            "frames": new_n,
            "old_counts": old_counts,
            "old_fps": old_fps,
            "new_counts": new_counts,
            "new_fps": new_fps,
        })

    print("\n" + "=" * 95)
    print("DETECTOR COMPARISON REPORT (Old: YOLO11n COCO vs New: YOLO11s IDD)")
    print("=" * 95)

    for r in results:
        print(f"\nClip: {r['folder']}/{r['clip']} (Frames analyzed: {r['frames']})")
        print(f"Old Model FPS: {r['old_fps']:.1f} | New Model FPS: {r['new_fps']:.1f}")
        print(f"{'Category':<16} | {'Old Model Count':<18} | {'New Model Count':<18} | {'Difference':<12}")
        print("-" * 72)
        for cat in categories:
            oc = r["old_counts"].get(cat, 0)
            nc = r["new_counts"].get(cat, 0)
            diff = nc - oc
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            print(f"{cat:<16} | {oc:<18} | {nc:<18} | {diff_str:<12}")

    print("\n" + "=" * 95)
    print("SUMMARY TABLE ACROSS ALL CLIPS")
    print("=" * 95)
    header = f"{'Clip':<26} | {'Frames':<6} | {'Old FPS':<7} | {'New FPS':<7} | {'AutoRick (N)':<12} | {'2Wheel (O/N)':<14} | {'Car (O/N)':<12} | {'Person (O/N)':<14}"
    print(header)
    print("-" * len(header))
    for r in results:
        oc = r["old_counts"]
        nc = r["new_counts"]
        print(
            f"{r['clip']:<26} | {r['frames']:<6} | {r['old_fps']:<7.1f} | {r['new_fps']:<7.1f} | "
            f"{nc.get('auto_rickshaw', 0):<12} | "
            f"{oc.get('two_wheeler', 0)} / {nc.get('two_wheeler', 0):<8} | "
            f"{oc.get('car', 0)} / {nc.get('car', 0):<6} | "
            f"{oc.get('person', 0)} / {nc.get('person', 0):<8}"
        )


if __name__ == "__main__":
    main()

