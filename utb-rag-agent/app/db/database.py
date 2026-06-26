"""
Capa SQLite con aiosqlite.
Tablas: queries, feedback.
Migración automática desde metrics.jsonl al primer arranque.
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

_PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = _PROJECT_ROOT / "data" / "metrics.db"
_JSONL_PATH = _PROJECT_ROOT / "data" / "metrics.jsonl"


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Context manager que abre una conexión, configura row_factory y WAL, y la cierra al salir."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        yield db


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS queries (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT    NOT NULL,
                session_id TEXT,
                message    TEXT    NOT NULL,
                best_score REAL    NOT NULL,
                escalated  INTEGER NOT NULL DEFAULT 0,
                latency_ms REAL,
                sources    TEXT    NOT NULL DEFAULT '[]'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT    NOT NULL,
                session_id TEXT    NOT NULL,
                message    TEXT    NOT NULL,
                answer     TEXT    NOT NULL,
                thumb      INTEGER NOT NULL,
                comment    TEXT
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_queries_ts ON queries(ts)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_queries_session ON queries(session_id)")
        # Migración de esquema: añadir columna channel si no existe
        try:
            await db.execute(
                "ALTER TABLE queries ADD COLUMN channel TEXT NOT NULL DEFAULT 'web'"
            )
        except Exception:
            pass  # columna ya existe
        await db.commit()

    await _migrate_jsonl()


async def _migrate_jsonl() -> None:
    """Importa el JSONL histórico a SQLite la primera vez (idempotente)."""
    if not _JSONL_PATH.exists():
        return

    async with get_db() as db:
        row = await db.execute_fetchall("SELECT COUNT(*) as n FROM queries")
        if row[0]["n"] > 0:
            return  # ya migrado

        records = []
        with _JSONL_PATH.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        if not records:
            return

        await db.executemany(
            """
            INSERT INTO queries (ts, session_id, message, best_score, escalated, sources)
            VALUES (:ts, :session_id, :message, :best_score, :escalated, :sources)
            """,
            [
                {
                    "ts": r["ts"],
                    "session_id": r.get("session_id"),
                    "message": r["message"],
                    "best_score": r["best_score"],
                    "escalated": 1 if r["escalated"] else 0,
                    "sources": json.dumps(r.get("sources", []), ensure_ascii=False),
                }
                for r in records
            ],
        )
        await db.commit()
        print(f"[db] Migrados {len(records)} registros desde metrics.jsonl")
