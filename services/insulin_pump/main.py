from libs.c2schema import now_iso

def emit_command(subject_id: str, actor_id: str, pubkey_id: str, parent_order_id: str, units: float = 1.5) -> dict:
    return {
        "event_type": "command",
        "subject_id": subject_id,
        "actor_id": actor_id,
        "payload": {"units": units},
        "parent_ids": [parent_order_id],
        "timestamp": now_iso(),
        "pubkey_id": pubkey_id,
        "sig": "",
        "expected_valid": True,
    }

def emit_invalid_command(subject_id: str, actor_id: str, pubkey_id: str) -> dict:
    return {
        "event_type": "command",
        "subject_id": subject_id,
        "actor_id": actor_id,
        "payload": {"units": 2.0},
        "parent_ids": [],
        "timestamp": now_iso(),
        "pubkey_id": pubkey_id,
        "sig": "",
        "expected_valid": False,
    }
