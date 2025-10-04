"""
Mock "contract" interface in Python.
This mirrors what an on-chain contract would expose,
but is implemented in-process for the demo.
"""
from typing import List, Tuple, Optional
from services.ledger.mock_ledger import MockLedger, OK

class C2LedgerContract:
    def __init__(self, secrets):
        self.ledger = MockLedger(secrets)

    def add_event(self, event: dict) -> Tuple[str, Optional[str]]:
        """Simulates calling a smart contract method to add an event."""
        return self.ledger.add_event(event)

    def get_event(self, event_id: str):
        return self.ledger.get_event(event_id)

    def get_ancestry(self, event_id: str):
        return self.ledger.get_ancestry(event_id)

    def export_graph(self):
        return self.ledger.export_graph()
