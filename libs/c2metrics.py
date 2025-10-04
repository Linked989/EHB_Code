import csv, os, time

class Metrics:
    """Append-only CSV logger with fixed header."""

    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_header = not os.path.exists(path)
        self._f = open(path, "a", newline="")
        self._w = csv.writer(self._f)
        if write_header:
            self._w.writerow(["ts","event_id","event_type","action","value","extra"])
            self._f.flush()

    def log(self, event_id: str, event_type: str, action: str, value: str, extra: str = "") -> None:
        self._w.writerow([time.time(), event_id, event_type, action, value, extra])
        self._f.flush()

    def close(self) -> None:
        try:
            self._f.close()
        except Exception:
            pass
