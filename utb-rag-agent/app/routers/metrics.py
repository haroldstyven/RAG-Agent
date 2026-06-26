import json
from pathlib import Path

from fastapi import APIRouter, Query

from app.schemas import MetricsSummary, QueryHistoryResponse, QueryRecord, Source

router = APIRouter(prefix="/metrics", tags=["metrics"])

_LOG_FILE = Path(__file__).parent.parent.parent / "data" / "metrics.jsonl"


def _load_records() -> list[dict]:
    if not _LOG_FILE.exists():
        return []
    records = []
    with _LOG_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


@router.get("/summary", response_model=MetricsSummary)
async def metrics_summary():
    records = _load_records()
    if not records:
        return MetricsSummary(
            total_queries=0, resolved=0, escalated=0,
            resolution_rate=0.0, avg_best_score=0.0,
        )
    escalated = sum(1 for r in records if r["escalated"])
    resolved = len(records) - escalated
    avg_score = sum(r["best_score"] for r in records) / len(records)
    return MetricsSummary(
        total_queries=len(records),
        resolved=resolved,
        escalated=escalated,
        resolution_rate=round(resolved / len(records) * 100, 1),
        avg_best_score=round(avg_score, 4),
    )


@router.get("/queries", response_model=QueryHistoryResponse)
async def query_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    records = _load_records()
    records.reverse()  # más recientes primero
    start = (page - 1) * page_size
    page_records = records[start : start + page_size]
    items = [
        QueryRecord(
            ts=r["ts"],
            session_id=r.get("session_id"),
            message=r["message"],
            best_score=r["best_score"],
            escalated=r["escalated"],
            sources=[Source(**s) for s in r.get("sources", [])],
        )
        for r in page_records
    ]
    return QueryHistoryResponse(
        total=len(records),
        page=page,
        page_size=page_size,
        items=items,
    )
