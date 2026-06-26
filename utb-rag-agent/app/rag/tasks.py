import uuid
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class IngestTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.QUEUED
    chunks_done: int = 0
    chunks_total: int = 0
    error: str | None = None

    @property
    def progress(self) -> float:
        if self.chunks_total == 0:
            return 0.0
        return round(self.chunks_done / self.chunks_total, 4)


_store: dict[str, IngestTask] = {}


def create_task() -> IngestTask:
    task = IngestTask()
    _store[task.id] = task
    return task


def get_task(task_id: str) -> IngestTask | None:
    return _store.get(task_id)
