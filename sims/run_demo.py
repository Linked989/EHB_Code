"""
Run a short end-to-end demo:
- Build a valid chain: observation -> order -> command -> outcome
- Attempt invalid commands (no parent) that should be rejected
- Exercise additional failure paths for policy metrics
- Export graph and metrics
"""
import json
from services.gateway.app import Gateway
from services.ecg_emulator.main import emit_observation
from services.doctor_console.main import emit_order
from services.insulin_pump.main import emit_command, emit_invalid_command
from services.glucose_monitor.main import emit_outcome
from libs.c2schema import compute_event_id, sign_event

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

    # Unauthorized actor attempt (command issued by ECG device)
    unauthorized = emit_command(subject, "PUMP#7", "PUMP#7_KEY", parent_order_id=eid_order, units=0.5)
    unauthorized["actor_id"] = "ECG#1"
    unauthorized["expected_valid"] = False
    status_unauth, eid_unauth = gw.submit(unauthorized)
    print("[unauthorized actor]", status_unauth, eid_unauth)

    # Missing parent reference (command points to non-existent event)
    missing_parent = emit_command(subject, "PUMP#7", "PUMP#7_KEY", parent_order_id="NON_EXISTENT_PARENT", units=0.5)
    missing_parent["expected_valid"] = False
    status_missing, eid_missing = gw.submit(missing_parent)
    print("[missing parent]", status_missing, eid_missing)

    # Wrong parent type (command referencing observation instead of order)
    wrong_parent = emit_command(subject, "PUMP#7", "PUMP#7_KEY", parent_order_id=eid_obs, units=0.8)
    wrong_parent["expected_valid"] = False
    status_wrong_parent, eid_wrong_parent = gw.submit(wrong_parent)
    print("[bad parent type]", status_wrong_parent, eid_wrong_parent)

    # Bad signature attempt (payload tampered after signing)
    tampered = emit_command(subject, "PUMP#7", "PUMP#7_KEY", parent_order_id=eid_order, units=1.0)
    tampered["expected_valid"] = False
    body = {k: v for k, v in tampered.items() if k != "sig"}
    tampered["sig"] = sign_event(body, SECRETS[tampered["pubkey_id"]])
    tampered["payload"]["units"] = 3.0  # tamper after signing
    tampered_id = compute_event_id(tampered)
    status_bad_sig, info_bad_sig = gw.contract.add_event(tampered)
    gw.metrics.log(
        tampered_id,
        tampered["event_type"],
        "submit",
        status_bad_sig,
        json.dumps({
            "info": info_bad_sig,
            "expected_valid": False,
            "latency_ms": None,
            "subject_id": tampered.get("subject_id"),
            "run_id": gw.run_id,
            "run_started": gw.run_started,
        }),
    )
    print("[bad signature]", status_bad_sig, tampered_id)

    # Export graph
    path = gw.export_graph("data/graph.json")
    print("Graph exported to", path)
    analytics = gw.build_reports("data")
    print("Metrics at data/metrics.csv")
    print("Analytics at", analytics)

if __name__ == "__main__":
    main()
