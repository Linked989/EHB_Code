import csv, os, time

class Metrics:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_header = not os.path.exists(path)
        self.f = open(path, "a", newline="")
        self.w = csv.writer(self.f)
        if write_header:
            self.w.writerow(["ts","event_id","event_type","action","value","extra"])

    def log(self, event_id, event_type, action, value, extra=""):
        self.w.writerow([time.time(), event_id, event_type, action, value, extra])
        self.f.flush()

    def close(self):
        try:
            self.f.close()
        except:
            pass
