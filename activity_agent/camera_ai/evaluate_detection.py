import cv2
from ultralytics import YOLO

model = YOLO("yolov8n.pt")
camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)

TP = FP = FN = TN = 0

print("P = Person байгаа")
print("N = Person байхгүй")
print("Q = Дуусгах")

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
                if conf >= 0.5:
                    predicted = True
                    confidence = max(confidence, conf)

    label = "PERSON DETECTED" if predicted else "NO PERSON"
    cv2.putText(frame, label, (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1,
                (0, 255, 0) if predicted else (0, 0, 255), 2)

    cv2.imshow("Detection Evaluation", frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord("p"):
        if predicted:
            TP += 1
        else:
            FN += 1
        print("P sample recorded")

    elif key == ord("n"):
        if predicted:
            FP += 1
        else:
            TN += 1
        print("N sample recorded")

    elif key == ord("q"):
        break

camera.release()
cv2.destroyAllWindows()

precision = TP / (TP + FP) if TP + FP else 0
recall = TP / (TP + FN) if TP + FN else 0
accuracy = (TP + TN) / (TP + FP + FN + TN) if TP + FP + FN + TN else 0

print("\n--- CAMERA QA RESULTS ---")
print("TP:", TP)
print("FP:", FP)
print("FN:", FN)
print("TN:", TN)
print("Precision:", round(precision, 3))
print("Recall:", round(recall, 3))
print("Accuracy:", round(accuracy, 3))