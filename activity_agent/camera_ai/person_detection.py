import json
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import cv2
import requests
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"
WEIGHTS_FILE = BASE_DIR / "yolov8n.pt"

with CONFIG_FILE.open("r", encoding="utf-8") as file:
    config = json.load(file)

API_URL = config["api_url"].rstrip("/").rsplit("/", 1)[0] + "/camera"
API_TOKEN = config["api_token"]
EMPLOYEE_ID = config["employee_id"]

CONFIDENCE_THRESHOLD = 0.5
STABLE_FRAMES = 5
RETRY_INTERVAL_SECONDS = 5


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def detect_person(results, confidence_threshold=CONFIDENCE_THRESHOLD):
    """Return whether a person is present and the highest qualifying confidence."""
    confidence = 0.0

    for result in results:
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue

        for box in boxes:
            if int(box.cls[0]) != 0:
                continue

            box_confidence = float(box.conf[0])
            if box_confidence >= confidence_threshold:
                confidence = max(confidence, box_confidence)

    return confidence > 0.0, confidence


def send_camera_event(is_present, confidence, timestamp=None):
    payload = {
        "employee_id": EMPLOYEE_ID,
        "timestamp": timestamp or utc_timestamp(),
        "event": json.dumps({
            "is_present": bool(is_present),
            "confidence": round(float(confidence), 3),
        }),
    }
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            API_URL,
            json=payload,
            headers=headers,
            timeout=config.get("request_timeout_seconds", 10),
        )
        if 200 <= response.status_code < 300:
            print("Camera event sent:", is_present)
            return True

        print("API error:", response.status_code, response.text[:300])
        if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
            return None
    except requests.RequestException as error:
        print("Camera API connection failed:", error)

    return False


def open_camera():
    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if camera.isOpened():
        return camera

    camera.release()
    camera = cv2.VideoCapture(0)
    if camera.isOpened():
        return camera

    camera.release()
    return None


def main():
    camera = None
    try:
        if not WEIGHTS_FILE.is_file():
            print(f"YOLO weights not found: {WEIGHTS_FILE}")
            return

        print("Loading YOLO model...")
        model = YOLO(str(WEIGHTS_FILE))

        camera = open_camera()
        if camera is None:
            print("Camera connection failed!")
            return

        last_enqueued_state = None
        candidate_state = None
        stable_count = 0
        pending_events = deque()
        next_send_attempt = 0.0

        print("Camera AI started. Press Q to quit.")

        while True:
            ret, frame = camera.read()
            if not ret:
                print("Cannot read camera frame.")
                break

            results = model(frame, verbose=False)
            predicted, confidence = detect_person(results)
            label = "PERSON" if predicted else "NO PERSON"

            cv2.putText(
                frame,
                label,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0) if predicted else (0, 0, 255),
                2,
            )
            cv2.imshow("Camera AI", frame)

            if predicted == candidate_state:
                stable_count += 1
            else:
                candidate_state = predicted
                stable_count = 1

            if stable_count >= STABLE_FRAMES and candidate_state != last_enqueued_state:
                pending_events.append({
                    "is_present": candidate_state,
                    "confidence": confidence,
                    "timestamp": utc_timestamp(),
                })
                last_enqueued_state = candidate_state

            now = time.monotonic()
            if pending_events and now >= next_send_attempt:
                event = pending_events[0]
                delivery = send_camera_event(
                    event["is_present"],
                    event["confidence"],
                    event["timestamp"],
                )
                if delivery is not False:
                    pending_events.popleft()
                next_send_attempt = time.monotonic() + RETRY_INTERVAL_SECONDS

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except (cv2.error, requests.RequestException) as error:
        print("Camera AI error:", error)
    finally:
        if camera is not None:
            camera.release()
        cv2.destroyAllWindows()
        print("Camera AI stopped.")


if __name__ == "__main__":
    main()
