from collections import deque
from dataclasses import dataclass, field

MAX_TURNS = 5  # turnos que se incluyen en el contexto


@dataclass
class Turn:
    role: str   # "user" | "assistant"
    content: str


@dataclass
class Session:
    turns: deque[Turn] = field(default_factory=lambda: deque(maxlen=MAX_TURNS * 2))

    def add(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=content))

    def format_history(self) -> str:
        if not self.turns:
            return ""
        lines = []
        for t in self.turns:
            prefix = "Estudiante" if t.role == "user" else "Asistente"
            lines.append(f"{prefix}: {t.content}")
        return "\n".join(lines)


# Store global en proceso — suficiente para demo; en producción usar Redis
_store: dict[str, Session] = {}


def get_session(session_id: str) -> Session:
    if session_id not in _store:
        _store[session_id] = Session()
    return _store[session_id]


def clear_session(session_id: str) -> None:
    _store.pop(session_id, None)
