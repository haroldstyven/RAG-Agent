"""
Logging de métricas: escribe en SQLite (primario) y mantiene JSONL como backup.
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from app.db.database import get_db

_LOG_FILE = Path(__file__).parent.parent.parent / "data" / "metrics.jsonl"


async def log_query(
    message: str,
    best_score: float,
    escalated: bool,
    session_id: str | None,
    sources: list[dict],
    latency_ms: float | None = None,
) -> None:
    ts = datetime.now(timezone.utc).isoformat()

    # SQLite (primario)
    async with await get_db() as db:
        await db.execute(
            """
            INSERT INTO queries (ts, session_id, message, best_score, escalated, latency_ms, sources)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                session_id,
                message,
                round(best_score, 4),
                1 if escalated else 0,
                round(latency_ms, 1) if latency_ms is not None else None,
                json.dumps(sources, ensure_ascii=False),
            ),
        )
        await db.commit()

    # JSONL backup
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": ts,
        "session_id": session_id,
        "message": message,
        "best_score": round(best_score, 4),
        "escalated": escalated,
        "sources": sources,
    }
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def log_feedback(
    session_id: str,
    message: str,
    answer: str,
    thumb: bool,
    comment: str | None,
) -> None:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    async with await get_db() as db:
        await db.execute(
            """
            INSERT INTO feedback (ts, session_id, message, answer, thumb, comment)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ts, session_id, message, answer, 1 if thumb else 0, comment),
        )
        await db.commit()
