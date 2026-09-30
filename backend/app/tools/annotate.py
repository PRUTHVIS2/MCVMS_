import argparse
import cv2
import time
from app.sources.filesource import FileSource
from app.sources.timesource import FileTimeSource
from app.vision.detector import Detector
from app.vision.tracker import Tracker

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input video file")
    parser.add_argument("output", help="Output annotated video file")
    args = parser.parse_args()
    
    print(f"Annotating {args.input} -> {args.output}")
    
    ts = FileTimeSource(0)
    source = FileSource(args.input, ts, paced=False)
    
    detector = Detector()
    tracker = Tracker(fps=int(source.fps))
    
    cap = cv2.VideoCapture(args.input)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(args.output, fourcc, source.fps, (width, height))
    
    frames_processed = 0
    start_time = time.time()
    
    batch_size = 16
    frame_batch = []
    ts_batch = []
    
    def process_batch():
        if not frame_batch:
            return
        
        batch_detections = detector.detect(frame_batch)
        for i in range(len(frame_batch)):
            frm = frame_batch[i]
            tms = ts_batch[i]
            dets = batch_detections[i]
            
            tracked = tracker.update(dets, frm, tms)
            
            for obj in tracked:
                x1, y1, x2, y2 = [int(v) for v in obj.xyxy]
                cv2.rectangle(frm, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{obj.cls} {obj.track_id}"
                cv2.putText(frm, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
            out.write(frm)
            
        frame_batch.clear()
        ts_batch.clear()
    
    for frame, ts_ms in source.iter_frames():
        frame_batch.append(frame)
        ts_batch.append(ts_ms)
        
        if len(frame_batch) >= batch_size:
            process_batch()
            frames_processed += batch_size
            print(f"Processed {frames_processed} frames...")
            
    # Process remaining
    if frame_batch:
        frames_processed += len(frame_batch)
        process_batch()
            
    out.release()
    elapsed = time.time() - start_time
    fps = frames_processed / elapsed if elapsed > 0 else 0
    print(f"Done. Processed {frames_processed} frames at {fps:.1f} FPS.")

if __name__ == "__main__":
    main()
