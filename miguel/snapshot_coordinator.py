"""Bounded snapshot coordination; persistence remains a separate layer."""
from __future__ import annotations
from enum import Enum
from threading import Condition
from time import monotonic
from typing import Callable, TypeVar

T = TypeVar("T")

class SnapshotState(str, Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    SNAPSHOTTING = "snapshotting"
    DURABLE = "durable"

class SnapshotTimeout(TimeoutError):
    pass

class SnapshotCoordinator:
    """Makes writes atomic with respect to a bounded priority freeze."""
    def __init__(self) -> None:
        self._condition = Condition()
        self._active_writers = 0
        self._freeze_requested = False
        self._sequence = 0
        self.state = SnapshotState.ACTIVE

    @property
    def sequence(self) -> int:
        with self._condition:
            return self._sequence

    def write(self, operation: Callable[[], T]) -> T:
        with self._condition:
            while self._freeze_requested:
                self._condition.wait()
            self._active_writers += 1
        try:
            return operation()
        finally:
            with self._condition:
                self._active_writers -= 1
                self._condition.notify_all()

    def snapshot(self, capture: Callable[[int], T], persist: Callable[[T], None], *, timeout: float = 5.0) -> T:
        deadline = monotonic() + timeout
        with self._condition:
            if self._freeze_requested:
                raise RuntimeError("snapshot already requested")
            self._freeze_requested = True
            while self._active_writers:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    self._freeze_requested = False
                    self.state = SnapshotState.ACTIVE
                    self._condition.notify_all()
                    raise SnapshotTimeout("could not quiesce writers")
                self._condition.wait(remaining)
            self._sequence += 1
            sequence = self._sequence
            self.state = SnapshotState.FROZEN
            try:
                self.state = SnapshotState.SNAPSHOTTING
                image = capture(sequence)
                persist(image)
                self.state = SnapshotState.DURABLE
                return image
            except BaseException:
                self.state = SnapshotState.ACTIVE
                raise
            finally:
                self._freeze_requested = False
                if self.state is SnapshotState.DURABLE:
                    self.state = SnapshotState.ACTIVE
                self._condition.notify_all()
