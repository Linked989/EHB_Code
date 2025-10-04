from typing import Dict, Optional, Tuple, List
from services.ledger.mock_ledger import MockLedger, OK

class C2LedgerContract:
    """Theoretical smart contract API backed by MockLedger."""

    def __init__(self, secrets: Dict[str, bytes]) -> None:
        self.ledger = MockLedger(secrets)

    def add_event(self, event: dict) -> Tuple[str, Optional[str]]:
        return self.ledger.add_event(event)

    def get_event(self, event_id: str):
        return self.ledger.get_event(event_id)

    def get_ancestry(self, event_id: str) -> List[str]:
        return self.ledger.get_ancestry(event_id)

    def export_graph(self) -> dict:
        return self.ledger.export_graph()
