"""
detector.py
-----------
Thin wrapper around a YOLOv8 model that returns a clean set of detected
label names (above a confidence threshold) for a single frame.
"""

from typing import List, Set
import math
import numpy as np


class ObjectDetector:
    def __init__(self, model_name: str = "yolov8n.pt", confidence_threshold: float = 0.45, model=None):
        if isinstance(confidence_threshold, bool) or not isinstance(confidence_threshold, (int, float)) or not math.isfinite(confidence_threshold) or not 0 < confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be greater than 0 and at most 1.")
        if model is None:
            from ultralytics import YOLO
            model = YOLO(model_name)
        self.model = model
        self.confidence_threshold = confidence_threshold

    def detect_labels(self, frame: np.ndarray) -> Set[str]:
        """Run detection on a frame and return the set of class names found
        above the confidence threshold."""
        return {detection['label'] for detection in self.detect_with_boxes(frame)}

    def detect_with_boxes(self, frame: np.ndarray) -> List[dict]:
        """Run detection and return full box info (label, confidence, xyxy),
        useful for drawing overlays."""
        results = self.model.predict(frame, conf=self.confidence_threshold, verbose=False,
                                     save=False, save_txt=False, save_crop=False, show=False)
        detections = []
        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                if conf >= self.confidence_threshold:
                    detections.append({
                        "label": self.model.names[int(box.cls[0])],
                        "confidence": conf,
                        "xyxy": box.xyxy[0].tolist(),
                    })
        return detections

    def detect_presence(self, frame: np.ndarray, person_label="person") -> dict:
        people = [d['confidence'] for d in self.detect_with_boxes(frame) if d['label'] == person_label]
        return {'present': bool(people), 'confidence': max(people, default=0.0)}
