from libs.c2schema import now_iso

def emit_observation(subject_id: str, actor_id: str, pubkey_id: str,
                     hr: int = 118, st_depression: float = 1.9, anomaly: bool = True) -> dict:
    return {
        "event_type": "observation",
        "subject_id": subject_id,
        "actor_id": actor_id,
        "payload": {"hr": hr, "st_depression": st_depression, "anomaly": anomaly},
        "parent_ids": [],
        "timestamp": now_iso(),
        "pubkey_id": pubkey_id,
        "sig": ""
    }
