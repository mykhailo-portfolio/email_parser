from typing import Optional, Dict, Protocol, List


# -----------------------------
# Minimal pointer storage (MVP)
# -----------------------------
class PointerStorage(Protocol):
    """Key-value interface for storing the last processed message id."""
    def get(self, key: str) -> Optional[str]: ...
    def set(self, key: str, value: str) -> None: ...

class InMemoryEmailStorage:
    """Simple in-memory storage for emails; swap with Redis later."""
    def __init__(self) -> None:
        self._data: Dict[str, str] = {}

    def get(self, key: str) -> Optional[str]:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
