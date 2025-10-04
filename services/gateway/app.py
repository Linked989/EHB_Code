from typing import Dict, Tuple
from libs.c2schema import now_iso, sign_event, compute_event_id
from libs.c2metrics import Metrics
from contracts.mock_contract import C2LedgerContract

class Gateway:
    """Signs events, submits to contract, logs status, exports graph."""

    def __init__(self, secrets: Dict[str, bytes], metrics_path: str = "data/metrics.csv") -> None:
        self.contract = C2LedgerContract(secrets)
        self.metrics = Metrics(metrics_path)
        self.secrets = secrets

    def submit(self, event: dict) -> Tuple[str, str]:
        event.setdefault("timestamp", now_iso())
        tmp_id = compute_event_id({k:v for k,v in event.items() if k != "sig"})
        secret = self.secrets[event["pubkey_id"]]
        event["sig"] = sign_event({k:v for k,v in event.items() if k != "sig"}, secret)
        status, info = self.contract.add_event(event)
        self.metrics.log(tmp_id, event["event_type"], "submit_status", status, str(info or ""))
        return status, tmp_id

    def export_graph(self, path: str = "data/graph.json") -> str:
        import json, os
        os.makedirs("data", exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.contract.export_graph(), f, indent=2)
        return path
