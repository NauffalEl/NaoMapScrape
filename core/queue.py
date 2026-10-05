"""Queue — FIFO of keyword x location jobs with status tracking."""

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class QueueStatus(str, Enum):
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class QueueItem:
    keyword: str
    location: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: QueueStatus = QueueStatus.WAITING
    collected: int = 0
    error: Optional[str] = None


class Queue:
    """FIFO queue with pause/resume and per-item status."""

    def __init__(self):
        self._items: List[QueueItem] = []
        self.paused = False

    def build(self, keywords: List[str], locations: List[str]) -> None:
        """Create the keyword x location cross-product of jobs."""
        self._items = [
            QueueItem(keyword=k, location=l)
            for k in keywords
            for l in locations
        ]

    def add(self, keyword: str, location: str) -> QueueItem:
        item = QueueItem(keyword=keyword, location=location)
        self._items.append(item)
        return item

    def next(self) -> Optional[QueueItem]:
        """Return the next WAITING item, or None if paused/empty."""
        if self.paused:
            return None
        for item in self._items:
            if item.status == QueueStatus.WAITING:
                return item
        return None

    def mark_running(self, item: QueueItem) -> None:
        item.status = QueueStatus.RUNNING

    def mark_complete(self, item: QueueItem, collected: int = 0) -> None:
        item.status = QueueStatus.COMPLETED
        item.collected = collected

    def mark_failed(self, item: QueueItem, error: str) -> None:
        item.status = QueueStatus.FAILED
        item.error = error

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def clear(self) -> None:
        self._items = []
        self.paused = False

    @property
    def items(self) -> List[QueueItem]:
        return self._items

    def stats(self) -> dict:
        return {
            "total": len(self._items),
            "waiting": sum(i.status == QueueStatus.WAITING for i in self._items),
            "running": sum(i.status == QueueStatus.RUNNING for i in self._items),
            "completed": sum(i.status == QueueStatus.COMPLETED for i in self._items),
            "failed": sum(i.status == QueueStatus.FAILED for i in self._items),
        }

    def __len__(self) -> int:
        return len(self._items)
