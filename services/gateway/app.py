from libs.c2schema import canonical_json, now_iso, sign_event, compute_event_id
from libs.c2metrics import Metrics
from services.ledger.mock_ledger import MockLedger, OK
import hashlib

class Gateway:
    def __init__(self, secrets, metrics_path="data/metrics.csv"):
        self.ledger = MockLedger(secrets)
        self.metrics = Metrics(metrics_path)
        self.secrets = secrets  # pubkey_id -> secret

    def submit(self, event: dict) -> tuple[str, str]:
        # Fill in timestamp if missing
        event.setdefault("timestamp", now_iso())
        # Compute temporary id for logging
        tmp_id = compute_event_id({k:v for k,v in event.items() if k != "sig"})
        # Sign with the device's secret (HMAC in this demo)
        secret = self.secrets[event["pubkey_id"]]
        event["sig"] = sign_event({k:v for k,v in event.items() if k != "sig"}, secret)
        status, info = self.ledger.add_event(event)
        self.metrics.log(tmp_id, event["event_type"], "submit_status", status, str(info or ""))
        return status, tmp_id

    def export_graph(self, path="data/graph.json"):
        import json, os
        os.makedirs("data", exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.ledger.export_graph(), f, indent=2)
        return path
