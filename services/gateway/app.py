import json
from time import perf_counter, time
from typing import Dict, Tuple
from libs.c2schema import now_iso, sign_event, compute_event_id
from libs.c2metrics import Metrics
from contracts.mock_contract import C2LedgerContract
from libs.c2analytics import build_reports

class Gateway:
    """Signs events, submits to contract, logs status, exports graph."""

    def __init__(self, secrets: Dict[str, bytes], metrics_path: str = "data/metrics.csv") -> None:
        self.contract = C2LedgerContract(secrets)
        self.metrics = Metrics(metrics_path)
        self.secrets = secrets
        self.metrics_path = metrics_path
        self.run_started = time()
        self.run_id = f"run-{int(self.run_started * 1000)}"

    def submit(self, event: dict) -> Tuple[str, str]:
        event.setdefault("timestamp", now_iso())
        tmp_id = compute_event_id({k:v for k,v in event.items() if k != "sig"})
        secret = self.secrets[event["pubkey_id"]]
        body = {k: v for k, v in event.items() if k != "sig"}
        event["sig"] = sign_event(body, secret)
        started = perf_counter()
        status, info = self.contract.add_event(event)
        latency_ms = (perf_counter() - started) * 1000.0
        extra = json.dumps({
            "info": info,
            "expected_valid": event.get("expected_valid", True),
            "latency_ms": latency_ms,
            "subject_id": event.get("subject_id"),
            "run_id": self.run_id,
            "run_started": self.run_started,
        })
        self.metrics.log(tmp_id, event["event_type"], "submit", status, extra)
        return status, tmp_id

    def export_graph(self, path: str = "data/graph.json") -> str:
        import json, os
        os.makedirs("data", exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.contract.export_graph(), f, indent=2)
        return path

    def build_reports(self, out_dir: str = "data", slo_p95_ms: float = 50.0) -> str:
        return build_reports(self.metrics_path, self.contract, out_dir, slo_p95_ms)
