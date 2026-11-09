import csv
from datetime import datetime
from pathlib import Path

import cv2
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
WEIGHTS_FILE = BASE_DIR / 'yolov8n.pt'
QA_FILE = BASE_DIR / 'qa_samples.csv'
CONFIDENCE_THRESHOLD = 0.5


def record_sample(actual, predicted, confidence):
    needs_header = not QA_FILE.exists() or QA_FILE.stat().st_size == 0
    with QA_FILE.open('a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if needs_header:
            writer.writerow(
                [
                    'timestamp',
                    'actual_present',
                    'predicted_present',
                    'confidence',
                ]
            )
        writer.writerow(
            [
                datetime.now().astimezone().isoformat(),
                int(actual),
                int(predicted),
                round(confidence, 3),
            ]
        )


def main():
    if not WEIGHTS_FILE.is_file():
        print(f'YOLO weights not found: {WEIGHTS_FILE}')
        return

    camera = None
    try:
        model = YOLO(str(WEIGHTS_FILE))
        camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not camera.isOpened():
            camera.release()
            camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            print('Camera connection failed!')
            return

        true_positive = false_positive = false_negative = true_negative = 0

        print('P = хүн байна')
        print('N = хүн байхгүй')
        print('Q = дуусгах')

        while True:
            ret, frame = camera.read()
            if not ret:
                print('Cannot read camera frame.')
                break

            results = model(frame, verbose=False)
            confidence = 0.0
            for result in results:
                boxes = getattr(result, 'boxes', None)
                if boxes is None:
                    continue
                for box in boxes:
                    if int(box.cls[0]) == 0:
                        box_confidence = float(box.conf[0])
                        if box_confidence >= CONFIDENCE_THRESHOLD:
                            confidence = max(confidence, box_confidence)

            predicted = confidence > 0.0
            label = 'PERSON DETECTED' if predicted else 'NO PERSON'
            cv2.putText(
                frame,
                label,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0) if predicted else (0, 0, 255),
                2,
            )
            cv2.imshow('Detection Evaluation', frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('p'):
                actual = True
            elif key == ord('n'):
                actual = False
            elif key == ord('q'):
                break
            else:
                continue

            record_sample(actual, predicted, confidence)
            if actual and predicted:
                true_positive += 1
            elif actual:
                false_negative += 1
            elif predicted:
                false_positive += 1
            else:
                true_negative += 1
            print('QA sample saved.')

    finally:
        if camera is not None:
            camera.release()
        cv2.destroyAllWindows()

    total = true_positive + false_positive + false_negative + true_negative
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0
    accuracy = (true_positive + true_negative) / total if total else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    print('\n--- CAMERA QA RESULTS ---')
    print('TP:', true_positive)
    print('FP:', false_positive)
    print('FN:', false_negative)
    print('TN:', true_negative)
    print('Precision:', round(precision, 3))
    print('Recall:', round(recall, 3))
    print('F1:', round(f1, 3))
    print('Accuracy:', round(accuracy, 3))


if __name__ == '__main__':
    main()
