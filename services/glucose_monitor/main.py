from libs.c2schema import now_iso

def emit_outcome(subject_id: str, actor_id: str, pubkey_id: str, parent_cmd_id: str, glucose_mgdl: int = 85) -> dict:
    return {
        "event_type": "outcome",
        "subject_id": subject_id,
        "actor_id": actor_id,
        "payload": {"glucose_mgdl": glucose_mgdl},
        "parent_ids": [parent_cmd_id],
        "timestamp": now_iso(),
        "pubkey_id": pubkey_id,
        "sig": ""
    }
