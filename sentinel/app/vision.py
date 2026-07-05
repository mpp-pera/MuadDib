import queue
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import streaming

_model = None
_model_lock = threading.Lock()


def _load_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            import torch
            from ultralytics import YOLO

            device = "cpu"
            if torch.cuda.is_available():
                try:
                    torch.zeros(1, device="cuda")
                    device = "cuda"
                except Exception:
                    device = "cpu"

            model = YOLO("yolov8n.pt")
            model.to(device)
            _model = (model, device)
            print(f"[vision] YOLOv8n loaded on {device}")
    return _model


@dataclass
class _Session:
    device_id: str
    stream_url: str
    stop_event: threading.Event = field(default_factory=threading.Event)
    latest: dict = field(default_factory=lambda: {"ts": 0, "width": 0, "height": 0, "boxes": []})
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        model, device = _load_model()
        broadcaster = streaming.get_broadcaster(self.device_id, self.stream_url)
        sub_id, q = broadcaster.subscribe()
        try:
            while not self.stop_event.is_set():
                try:
                    jpg = q.get(timeout=1.0)
                except queue.Empty:
                    continue

                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                h, w = frame.shape[:2]
                results = model.predict(frame, device=device, verbose=False)[0]
                boxes = []
                for box in results.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    boxes.append({
                        "label": model.names[int(box.cls[0])],
                        "conf": round(float(box.conf[0]), 2),
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    })

                with self.lock:
                    self.latest = {"ts": time.time(), "width": w, "height": h, "boxes": boxes}
        finally:
            broadcaster.unsubscribe(sub_id)

    def get_latest(self) -> dict:
        with self.lock:
            return dict(self.latest)


_sessions: dict[str, _Session] = {}
_sessions_lock = threading.Lock()


def enable(device_id: str, stream_url: str) -> None:
    with _sessions_lock:
        if device_id in _sessions:
            return
        session = _Session(device_id=device_id, stream_url=stream_url)
        _sessions[device_id] = session
        session.start()


def disable(device_id: str) -> None:
    with _sessions_lock:
        session = _sessions.pop(device_id, None)
    if session is not None:
        session.stop_event.set()


def get_tags(device_id: str) -> dict | None:
    with _sessions_lock:
        session = _sessions.get(device_id)
    if session is None:
        return None
    return session.get_latest()
