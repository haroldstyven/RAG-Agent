import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

MAX_TURNS = 5  # turnos que se incluyen en el contexto


@dataclass
class Turn:
    role: str   # "user" | "assistant"
    content: str


@dataclass
class Session:
    turns: deque[Turn] = field(default_factory=lambda: deque(maxlen=MAX_TURNS * 2))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def add(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=content))
        self.updated_at = time.time()

    def format_history(self) -> str:
        if not self.turns:
            return ""
        lines = []
        for t in self.turns:
            prefix = "Estudiante" if t.role == "user" else "Asistente"
            lines.append(f"{prefix}: {t.content}")
        return "\n".join(lines)

    def last_user_message(self) -> str | None:
        for t in reversed(self.turns):
            if t.role == "user":
                return t.content[:100]
        return None


# Store global en proceso — suficiente para demo; en producción usar Redis
_store: dict[str, Session] = {}


def get_session(session_id: str) -> Session:
    if session_id not in _store:
        _store[session_id] = Session()
    return _store[session_id]


def clear_session(session_id: str) -> None:
    _store.pop(session_id, None)


async def persist_turn(session_id: str, role: str, content: str) -> None:
    from app.db.database import get_db
    ts = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO session_turns (session_id, ts, role, content) VALUES (?, ?, ?, ?)",
            (session_id, ts, role, content),
        )
        await db.commit()


async def load_sessions_from_db() -> None:
    """Restaura las últimas 100 sesiones desde SQLite al iniciar el servidor."""
    from app.db.database import get_db
    async with get_db() as db:
        meta_rows = await db.execute_fetchall(
            """
            SELECT session_id, MIN(ts) AS created_at, MAX(ts) AS updated_at
            FROM session_turns
            GROUP BY session_id
            ORDER BY updated_at DESC
            LIMIT 100
            """
        )
        if not meta_rows:
            return

        for row in meta_rows:
            sid = row["session_id"]
            turn_rows = await db.execute_fetchall(
                """
                SELECT role, content FROM (
                    SELECT role, content, ts
                    FROM session_turns
                    WHERE session_id = ?
                    ORDER BY ts DESC
                    LIMIT ?
                ) ORDER BY ts ASC
                """,
                (sid, MAX_TURNS * 2),
            )
            sess = Session()
            sess.created_at = datetime.fromisoformat(row["created_at"]).timestamp()
            sess.updated_at = datetime.fromisoformat(row["updated_at"]).timestamp()
            for t in turn_rows:
                sess.turns.append(Turn(role=t["role"], content=t["content"]))
            _store[sid] = sess

    print(f"[memory] Restauradas {len(meta_rows)} sesiones desde SQLite")
