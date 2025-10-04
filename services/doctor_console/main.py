from libs.c2schema import now_iso
def emit_order(subject_id: str, actor_id: str, pubkey_id: str, parent_obs_id: str, dose_units=1.5):
    return {
        "event_type": "order",
        "subject_id": subject_id,
        "actor_id": actor_id,
        "payload": {"med": "insulin", "dose_units": dose_units},
        "parent_ids": [parent_obs_id],
        "timestamp": now_iso(),
        "pubkey_id": pubkey_id,
        "sig": ""
    }
