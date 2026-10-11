import queue
import threading
from typing import Any, Dict, Optional


class EventEmitter:
    def __init__(self, event_queue: queue.Queue):
        self.queue = event_queue
        self._local = threading.local()

    @property
    def active_service(self) -> Optional[str]:
        return getattr(self._local, "active_service", None)

    @active_service.setter
    def active_service(self, service_name: Optional[str]):
        self._local.active_service = service_name

    def emit(self, event_type: str, data: Dict[str, Any]):
        self.queue.put((event_type, data))

    def emit_log(self, text: str):
        if not text:
            return
        self.emit(
            "service_log",
            {
                "service": self.active_service,
                "text": text,
            },
        )


class QueueLogWriter:
    def __init__(self, emitter: EventEmitter):
        self.emitter = emitter

    def write(self, text: str) -> int:
        if text:
            payload = {
                "service": self.emitter.active_service,
                "text": text,
            }
            self.emitter.emit("service_log", payload)
        return len(text)

    def flush(self):
        pass
