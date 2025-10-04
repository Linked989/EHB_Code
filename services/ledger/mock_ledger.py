from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set
from libs.c2schema import PARENT_RULES, actor_allowed, compute_event_id, verify_sig

OK = "OK"
ERR_MISSING_PARENT = "ERR_MISSING_PARENT"
ERR_BAD_PARENT_TYPE = "ERR_BAD_PARENT_TYPE"
ERR_UNAUTHORIZED = "ERR_UNAUTHORIZED"
ERR_CYCLE = "ERR_CYCLE"
ERR_DUPLICATE = "ERR_DUPLICATE"
ERR_PARENT_REQUIRED = "ERR_PARENT_REQUIRED"

@dataclass
class EventRecord:
    event_id: str
    event_type: str
    parent_ids: List[str]
    actor_id: str
    subject_id: str
    payload: dict
    timestamp: str
    pubkey_id: str
    sig: str

class MockLedger:
    """In-memory store with causal validation."""

    def __init__(self, secrets: Dict[str, bytes]) -> None:
        self.secrets = secrets                     # pubkey_id -> secret
        self.events: Dict[str, EventRecord] = {}
        self.types: Dict[str, str] = {}           # event_id -> event_type
        self.children: Dict[str, List[str]] = {}  # parent_id -> [child_ids]

    def exists(self, eid: str) -> bool:
        return eid in self.events

    def type_of(self, eid: str) -> Optional[str]:
        return self.types.get(eid)

    def _introduces_cycle(self, eid: str, parents: List[str]) -> bool:
        """DFS from parents; if eid is reachable, adding eid creates a cycle."""
        visited: Set[str] = set()
        def dfs(x: str) -> bool:
            if x == eid: return True
            if x in visited: return False
            visited.add(x)
            for c in self.children.get(x, []):
                if dfs(c): return True
            return False
        return any(dfs(p) for p in parents)

    def add_event(self, event: dict) -> Tuple[str, Optional[str]]:
        """Validate and commit. Returns (status, info)."""
        pub = event["pubkey_id"]
        if pub not in self.secrets:
            return ERR_UNAUTHORIZED, "unknown_pubkey"
        if not verify_sig({k:v for k,v in event.items() if k != "sig"}, event["sig"], self.secrets[pub]):
            return ERR_UNAUTHORIZED, "bad_signature"

        eid = compute_event_id(event)
        if eid in self.events:
            return ERR_DUPLICATE, None

        et = event["event_type"]
        if not actor_allowed(event["actor_id"], et):
            return ERR_UNAUTHORIZED, "actor_not_allowed"

        parents = event.get("parent_ids", [])
        allowed = PARENT_RULES.get(et, [])
        if allowed and not parents:
            return ERR_PARENT_REQUIRED, et
        for p in parents:
            if not self.exists(p):
                return ERR_MISSING_PARENT, p
        for p in parents:
            pt = self.type_of(p)
            if pt not in allowed:
                return ERR_BAD_PARENT_TYPE, f"{pt} -> {et}"

        if self._introduces_cycle(eid, parents):
            return ERR_CYCLE, None

        rec = EventRecord(
            event_id=eid,
            event_type=et,
            parent_ids=parents,
            actor_id=event["actor_id"],
            subject_id=event["subject_id"],
            payload=event.get("payload", {}),
            timestamp=event["timestamp"],
            pubkey_id=pub,
            sig=event["sig"],
        )
        self.events[eid] = rec
        self.types[eid] = et
        for p in parents:
            self.children.setdefault(p, []).append(eid)
        self.children.setdefault(eid, [])
        return OK, None

    def get_event(self, eid: str) -> Optional[EventRecord]:
        return self.events.get(eid)

    def get_ancestry(self, eid: str) -> List[str]:
        """Return root→...→eid following the first parent at each step."""
        path: List[str] = []
        seen: Set[str] = set()
        cur = self.events.get(eid)
        while cur and cur.event_id not in seen:
            path.append(cur.event_id)
            seen.add(cur.event_id)
            if cur.parent_ids:
                cur = self.events.get(cur.parent_ids[0])
            else:
                break
        return list(reversed(path))

    def export_graph(self) -> dict:
        nodes = [{"id": eid, "type": rec.event_type, "actor": rec.actor_id} for eid, rec in self.events.items()]
        links = [{"source": p, "target": eid} for eid, rec in self.events.items() for p in rec.parent_ids]
        return {"nodes": nodes, "links": links}
