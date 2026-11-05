import cv2
import csv
from pathlib import Path
from datetime import datetime
from ultralytics import YOLO

CONFIDENCE_THRESHOLD = 0.5

CSV_FILE = Path(__file__).resolve().parent.parent / "qa_samples.csv"


def save_sample(actual, predicted, confidence):
    new_file = not CSV_FILE.exists()

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if new_file:
            writer.writerow([
                "timestamp",
                "actual_present",
                "predicted_present",
                "confidence"
            ])

        writer.writerow([
            datetime.now().isoformat(),
            int(actual),
            int(predicted),
            round(confidence, 3)
        ])


def main():
    print("Loading YOLO model...")
    model = YOLO("yolov8n.pt")

    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    if not camera.isOpened():
        print("Camera connection failed!")
        return

    tp = fp = fn = tn = 0

    print("P = Person present")
    print("N = No person")
    print("Q = Quit")

    try:
        while True:
            ret, frame = camera.read()
            if not ret:
                break

            results = model(frame, verbose=False)

            predicted = False
            confidence = 0.0

            for result in results:
                for box in result.boxes:
                    if int(box.cls[0]) == 0:
                        conf = float(box.conf[0])
                        if conf >= CONFIDENCE_THRESHOLD:
                            predicted = True
                            confidence = max(confidence, conf)

            label = "PERSON" if predicted else "NO PERSON"

            cv2.putText(
                frame, label, (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1,
                (0, 255, 0) if predicted else (0, 0, 255), 2
            )

            cv2.imshow("Camera QA", frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break

            elif key == ord("p"):
                actual = True
            elif key == ord("n"):
                actual = False
            else:
                continue

            save_sample(actual, predicted, confidence)

            if actual and predicted:
                tp += 1
                print("TP")
            elif actual and not predicted:
                fn += 1
                print("FN")
            elif not actual and predicted:
                fp += 1
                print("FP")
            else:
                tn += 1
                print("TN")

            print("Sample saved to qa_samples.csv")

    finally:
        camera.release()
        cv2.destroyAllWindows()

        total = tp + fp + fn + tn
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        accuracy = (tp + tn) / total if total else 0

        print("\n===== CAMERA QA RESULTS =====")
        print("TP:", tp)
        print("FP:", fp)
        print("FN:", fn)
        print("TN:", tn)
        print(f"Precision: {precision:.3f}")
        print(f"Recall: {recall:.3f}")
        print(f"Accuracy: {accuracy:.3f}")


if __name__ == "__main__":
    main()