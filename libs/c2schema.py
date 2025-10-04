from datetime import datetime, timezone
import json, hashlib, hmac
from typing import Dict, List

PARENT_RULES: Dict[str, List[str]] = {
    "observation": [],
    "diagnosis": ["observation"],
    "order": ["observation", "diagnosis"],
    "command": ["order"],
    "outcome": ["command"],
}

ALLOWED_ACTORS: Dict[str, List[str]] = {
    "observation": ["ECG", "GLUCOSE"],
    "diagnosis":  ["DOCTOR"],
    "order":      ["DOCTOR"],
    "command":    ["PUMP"],
    "outcome":    ["GLUCOSE"],
}

def canonical_json(obj: dict) -> str:
    """Return deterministic JSON (sorted keys, no spaces)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))

def sha256_hex(b: bytes) -> str:
    """SHA-256 hex digest."""
    return hashlib.sha256(b).hexdigest()

def now_iso() -> str:
    """UTC ISO-8601 timestamp with timezone."""
    return datetime.now(timezone.utc).isoformat()

def sign_event(event: dict, secret: bytes) -> str:
    """HMAC-SHA256 over canonical JSON of event EXCLUDING 'sig'."""
    msg = canonical_json(event).encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()

def verify_sig(event: dict, sig_hex: str, secret: bytes) -> bool:
    """Verify HMAC-SHA256 for event EXCLUDING 'sig'."""
    msg = canonical_json(event).encode()
    mac = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, sig_hex)

def compute_event_id(event: dict) -> str:
    """Hash of the event EXCLUDING 'sig' field."""
    to_hash = {k: v for k, v in event.items() if k != "sig"}
    return sha256_hex(canonical_json(to_hash).encode())

def actor_allowed(actor_id: str, event_type: str) -> bool:
    """Prefix-based authorization check."""
    return any(actor_id.startswith(p) for p in ALLOWED_ACTORS.get(event_type, []))
