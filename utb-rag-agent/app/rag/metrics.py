import json
from datetime import datetime, timezone
from pathlib import Path

_LOG_FILE = Path(__file__).parent.parent.parent / "data" / "metrics.jsonl"


def log_query(
    message: str,
    best_score: float,
    escalated: bool,
    session_id: str | None,
    sources: list[dict],
) -> None:
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "message": message,
        "best_score": round(best_score, 4),
        "escalated": escalated,
        "sources": sources,
    }
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
