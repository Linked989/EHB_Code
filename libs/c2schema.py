import json
import hashlib
import hmac
from datetime import datetime, timezone

# Simple canonical JSON for hashing/signing
def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))

def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# Simulated signature scheme using HMAC (replace with ed25519 later)
def sign_event(event: dict, secret: bytes) -> str:
    msg = canonical_json(event).encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()

def verify_sig(event: dict, sig_hex: str, secret: bytes) -> bool:
    msg = canonical_json(event).encode()
    mac = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, sig_hex)

# Event rules
PARENT_RULES = {
    "observation": [],
    "diagnosis": ["observation"],
    "order": ["observation", "diagnosis"],
    "command": ["order"],
    "outcome": ["command"],
}

ALLOWED_ACTORS = {
    # event_type -> list of actor prefixes allowed
    "observation": ["ECG", "GLUCOSE"],
    "diagnosis": ["DOCTOR"],
    "order": ["DOCTOR"],
    "command": ["PUMP"],
    "outcome": ["GLUCOSE"],
}

def actor_allowed(actor_id: str, event_type: str) -> bool:
    prefixes = ALLOWED_ACTORS.get(event_type, [])
    return any(actor_id.startswith(p) for p in prefixes)

def compute_event_id(event: dict) -> str:
    # Event ID is hash of selected immutable fields (without signature)
    to_hash = {k: event[k] for k in event if k != "sig"}
    return sha256_hex(canonical_json(to_hash).encode())
