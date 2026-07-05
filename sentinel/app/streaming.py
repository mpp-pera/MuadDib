import queue
import threading
import time

import requests

_JPEG_SOI = b"\xff\xd8"
_JPEG_EOI = b"\xff\xd9"
_MAX_BUFFER = 2_000_000  # guards against unbounded growth if the stream sends non-JPEG garbage


class Broadcaster:
    """Pulls a single MJPEG connection from a device and fans decoded JPEG frames
    out to any number of subscribers (browser viewers, the object detector).

    The ESP32 camera firmware doesn't reliably tolerate more than one concurrent
    client on its stream endpoint, so every consumer in this process shares one
    upstream connection instead of each opening its own.
    """

    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self._lock = threading.Lock()
        self._subs: dict[int, "queue.Queue[bytes]"] = {}
        self._next_id = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def subscribe(self) -> tuple[int, "queue.Queue[bytes]"]:
        with self._lock:
            sub_id = self._next_id
            self._next_id += 1
            q: queue.Queue = queue.Queue(maxsize=2)
            self._subs[sub_id] = q
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
        return sub_id, q

    def unsubscribe(self, sub_id: int) -> None:
        with self._lock:
            self._subs.pop(sub_id, None)
            should_stop = not self._subs
        if should_stop:
            self._stop.set()

    def _publish(self, jpg: bytes) -> None:
        with self._lock:
            subs = list(self._subs.values())
        for q in subs:
            try:
                while q.full():
                    q.get_nowait()
                q.put_nowait(jpg)
            except Exception:
                pass

    def _run(self) -> None:
        backoff = 1.0
        max_backoff = 15.0
        while not self._stop.is_set():
            resp = None
            got_frame = False
            try:
                resp = requests.get(self.stream_url, stream=True, timeout=(5, 10))
                buf = b""
                for chunk in resp.iter_content(chunk_size=4096):
                    if self._stop.is_set():
                        break
                    buf += chunk

                    newest = None
                    while True:
                        start = buf.find(_JPEG_SOI)
                        if start == -1:
                            break
                        end = buf.find(_JPEG_EOI, start + 2)
                        if end == -1:
                            break
                        newest = buf[start:end + 2]
                        buf = buf[end + 2:]

                    if newest is not None:
                        got_frame = True
                        backoff = 1.0
                        self._publish(newest)

                    if len(buf) > _MAX_BUFFER:
                        buf = buf[-_MAX_BUFFER:]
            except Exception as e:
                print(f"[stream] error for {self.stream_url}: {e}")
            finally:
                if resp is not None:
                    resp.close()

            if self._stop.is_set():
                break
            if got_frame:
                time.sleep(0.05)
            else:
                print(f"[stream] no frames from {self.stream_url}, retrying in {backoff:.0f}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)


_broadcasters: dict[str, Broadcaster] = {}
_registry_lock = threading.Lock()


def get_broadcaster(device_id: str, stream_url: str) -> Broadcaster:
    with _registry_lock:
        b = _broadcasters.get(device_id)
        if b is None or b.stream_url != stream_url:
            b = Broadcaster(stream_url)
            _broadcasters[device_id] = b
        return b


def drop(device_id: str) -> None:
    with _registry_lock:
        _broadcasters.pop(device_id, None)
