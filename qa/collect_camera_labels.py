"""Collect human presence labels plus YOLO scalars; never save an image/video."""
import argparse
import csv
from datetime import datetime
import os
from pathlib import Path
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--consent', action='store_true', required=True, help='Explicit permission to open this webcam session.')
    parser.add_argument('--output', type=Path, default=Path('.runtime/qa/camera-labeled.csv'))
    parser.add_argument('--camera-index', type=int, default=0)
    parser.add_argument('--model', default='yolov8n.pt')
    parser.add_argument('--threshold', type=float, default=.45)
    args = parser.parse_args()
    import cv2
    from src.detector import ObjectDetector
    detector = ObjectDetector(args.model, args.threshold)
    cap = cv2.VideoCapture(args.camera_index)
    fields = ['sample_id', 'data_kind', 'timestamp', 'expected', 'predicted', 'confidence']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stream = None
    count = 0
    try:
        if not cap.isOpened():
            raise RuntimeError('Camera unavailable. Check OS permission and camera index.')
        if args.output.exists() and args.output.stat().st_size:
            with args.output.open(newline='', encoding='utf-8') as source:
                if next(csv.reader(source)) != fields:
                    parser.error('Existing label file has a different schema; use another output path.')
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        stream = os.fdopen(fd, 'a', newline='', encoding='utf-8')
        writer = csv.DictWriter(stream, fieldnames=fields)
        if args.output.stat().st_size == 0:
            writer.writeheader(); stream.flush()
        print('Assign truth BEFORE inference. p=person currently visible, a=no person, q=finish.')
        print('Vary lighting, distance and occlusion. Predictions are hidden until the label is recorded.')
        while True:
            truth = input('Human expected label [p/a/q]: ').strip().lower()
            if truth == 'q': break
            if truth not in {'p', 'a'}: continue
            # Drain old buffered frames after the operator changes position.
            for _ in range(8):
                ok, frame = cap.read()
            if not ok:
                raise RuntimeError('Could not read camera frame.')
            result = detector.detect_presence(frame)
            writer.writerow({'sample_id': uuid.uuid4().hex, 'data_kind': 'real',
                'timestamp': datetime.now().astimezone().isoformat(), 'expected': int(truth == 'p'),
                'predicted': int(result['present']), 'confidence': result['confidence']})
            stream.flush(); count += 1
            print(f"Recorded metadata sample {count}; predicted={int(result['present'])} confidence={result['confidence']:.3f}")
    finally:
        cap.release()
        if stream: stream.close()
        print(f'{count} human-labeled samples added; no frames/video saved.')


if __name__ == '__main__':
    main()
