"""
detector.py
-----------
Thin wrapper around a YOLOv8 model that returns a clean set of detected
label names (above a confidence threshold) for a single frame.
"""

from typing import List, Set
import numpy as np
from ultralytics import YOLO


class ObjectDetector:
    def __init__(self, model_name: str = "yolov8n.pt", confidence_threshold: float = 0.45):
        self.model = YOLO(model_name)
        self.confidence_threshold = confidence_threshold

    def detect_labels(self, frame: np.ndarray) -> Set[str]:
        """Run detection on a frame and return the set of class names found
        above the confidence threshold."""
        results = self.model(frame, verbose=False)
        labels: Set[str] = set()
        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                if conf >= self.confidence_threshold:
                    cls_name = self.model.names[int(box.cls[0])]
                    labels.add(cls_name)
        return labels

    def detect_with_boxes(self, frame: np.ndarray) -> List[dict]:
        """Run detection and return full box info (label, confidence, xyxy),
        useful for drawing overlays."""
        results = self.model(frame, verbose=False)
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
