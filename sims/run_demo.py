"""
Run a short end-to-end demo:
- Build a valid chain: observation -> order -> command -> outcome
- Attempt invalid commands (no parent) that should be rejected
- Export graph and metrics
"""
from services.gateway.app import Gateway
from services.ecg_emulator.main import emit_observation
from services.doctor_console.main import emit_order
from services.insulin_pump.main import emit_command, emit_invalid_command
from services.glucose_monitor.main import emit_outcome
from libs.c2schema import compute_event_id

SECRETS = {
    "ECG#1_KEY": b"ecg_secret",
    "DOCTOR#A_KEY": b"doctor_secret",
    "PUMP#7_KEY": b"pump_secret",
    "GLUCOSE#1_KEY": b"glucose_secret",
}

def main():
    gw = Gateway(SECRETS, metrics_path="data/metrics.csv")
    subject = "S123"

    # 1) Observation
    obs = emit_observation(subject, "ECG#1", "ECG#1_KEY", hr=118, st_depression=1.9, anomaly=True)
    status, eid_obs = gw.submit(obs)
    print("[obs]", status, eid_obs)

    # 2) Order
    order = emit_order(subject, "DOCTOR#A", "DOCTOR#A_KEY", parent_obs_id=eid_obs, dose_units=1.5)
    status, eid_order = gw.submit(order)
    print("[order]", status, eid_order)

    # 3) Command
    cmd = emit_command(subject, "PUMP#7", "PUMP#7_KEY", parent_order_id=eid_order, units=1.5)
    status, eid_cmd = gw.submit(cmd)
    print("[command]", status, eid_cmd)

    # 4) Outcome
    out = emit_outcome(subject, "GLUCOSE#1", "GLUCOSE#1_KEY", parent_cmd_id=eid_cmd, glucose_mgdl=85)
    status, eid_out = gw.submit(out)
    print("[outcome]", status, eid_out)

    # Invalid attempts
    bad = emit_invalid_command(subject, "PUMP#7", "PUMP#7_KEY")
    status, eid_bad = gw.submit(bad)
    print("[invalid command]", status, eid_bad)

    # Export graph
    path = gw.export_graph("data/graph.json")
    print("Graph exported to", path)
    analytics = gw.build_reports("data")
    print("Metrics at data/metrics.csv")
    print("Analytics at", analytics)

if __name__ == "__main__":
    main()
