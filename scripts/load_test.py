"""
Simple load test:
- Replays N chains of Observation->Order->Command->Outcome
- Injects invalid commands at a configurable ratio
- Measures success/failure counts and writes metrics
"""
import argparse, time, random
from services.gateway.app import Gateway
from services.ecg_emulator.main import emit_observation
from services.doctor_console.main import emit_order
from services.insulin_pump.main import emit_command, emit_invalid_command
from services.glucose_monitor.main import emit_outcome

SECRETS = {
    "ECG#1_KEY": b"ecg_secret",
    "DOCTOR#A_KEY": b"doctor_secret",
    "PUMP#7_KEY": b"pump_secret",
    "GLUCOSE#1_KEY": b"glucose_secret",
}

def one_chain(gw, subject="S123", invalid_prob=0.2):
    ok = 0; bad = 0
    # Observation
    st, obs_id = gw.submit(emit_observation(subject, "ECG#1", "ECG#1_KEY", hr=60+random.randint(0,80), st_depression=round(random.random()*2,2), anomaly=True))
    ok += int(st=="OK"); bad += int(st!="OK")
    # Order
    st, order_id = gw.submit(emit_order(subject, "DOCTOR#A", "DOCTOR#A_KEY", parent_obs_id=obs_id, dose_units=round(1+random.random(),2)))
    ok += int(st=="OK"); bad += int(st!="OK")
    # Command (sometimes invalid)
    if random.random() < invalid_prob:
        st, cmd_id = gw.submit(emit_invalid_command(subject, "PUMP#7", "PUMP#7_KEY"))
    else:
        st, cmd_id = gw.submit(emit_command(subject, "PUMP#7", "PUMP#7_KEY", parent_order_id=order_id, units=round(1+random.random(),2)))
    if st=="OK":
        ok += 1
        # Outcome only if command was valid
        st, out_id = gw.submit(emit_outcome(subject, "GLUCOSE#1", "GLUCOSE#1_KEY", parent_cmd_id=cmd_id, glucose_mgdl=80+random.randint(-10,10)))
        ok += int(st=="OK"); bad += int(st!="OK")
    else:
        bad += 1
    return ok, bad

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", type=int, default=50)
    ap.add_argument("--invalid-prob", type=float, default=0.2)
    args = ap.parse_args()

    gw = Gateway(SECRETS, metrics_path="data/metrics.csv")

    t0 = time.time()
    ok_sum = bad_sum = 0
    for _ in range(args.chains):
        ok, bad = one_chain(gw, invalid_prob=args.invalid_prob)
        ok_sum += ok; bad_sum += bad
    elapsed = time.time() - t0
    eps = (ok_sum+bad_sum)/elapsed if elapsed>0 else 0.0
    print(f"events_ok={ok_sum} events_bad={bad_sum} elapsed_sec={elapsed:.2f} events_per_sec={eps:.2f}")
    gw.export_graph("data/graph.json")

if __name__ == "__main__":
    main()
