import cv2
import numpy as np
import argparse

def main():
    parser = argparse.ArgumentParser(description="Make a synthetic clip with moving boxes")
    parser.add_argument("out", help="Output MP4 file")
    parser.add_argument("--frames", type=int, default=150, help="Number of frames")
    parser.add_argument("--fps", type=int, default=25, help="FPS")
    args = parser.parse_args()
    
    width, height = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(args.out, fourcc, args.fps, (width, height))
    
    box1 = {'pos': [100, 360], 'color': (0, 0, 255), 'speed': [5, 0], 'size': 50}
    box2 = {'pos': [1180, 200], 'color': (255, 0, 0), 'speed': [-4, 2], 'size': 80}
    
    for i in range(args.frames):
        frame = np.ones((height, width, 3), dtype=np.uint8) * 50
        
        # update pos
        box1['pos'][0] += box1['speed'][0]
        box1['pos'][1] += box1['speed'][1]
        
        box2['pos'][0] += box2['speed'][0]
        box2['pos'][1] += box2['speed'][1]
        
        # draw box1
        x, y = int(box1['pos'][0]), int(box1['pos'][1])
        s = box1['size']
        cv2.rectangle(frame, (x, y), (x+s, y+s), box1['color'], -1)
        
        # draw box2
        x, y = int(box2['pos'][0]), int(box2['pos'][1])
        s = box2['size']
        cv2.rectangle(frame, (x, y), (x+s, y+s), box2['color'], -1)
        
        out.write(frame)
        
    out.release()
    print(f"Saved {args.frames} frames to {args.out}")

if __name__ == "__main__":
    main()
