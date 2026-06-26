import json

from fastapi import APIRouter, Query

from app.db.database import get_db
from app.schemas import MetricsSummary, QueryHistoryResponse, QueryRecord, Source

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary", response_model=MetricsSummary)
async def metrics_summary(
    desde: str | None = Query(None, description="ISO date, e.g. 2026-01-01"),
    hasta: str | None = Query(None, description="ISO date, e.g. 2026-12-31"),
):
    async with await get_db() as db:
        where, params = _date_filter(desde, hasta)

        row = await db.execute_fetchall(
            f"""
            SELECT
                COUNT(*)                          AS total,
                SUM(CASE WHEN escalated=0 THEN 1 ELSE 0 END) AS resolved,
                SUM(escalated)                    AS escalated,
                AVG(best_score)                   AS avg_score
            FROM queries {where}
            """,
            params,
        )
        r = row[0]
        total = r["total"] or 0
        if total == 0:
            return MetricsSummary(
                total_queries=0, resolved=0, escalated=0,
                resolution_rate=0.0, avg_best_score=0.0,
                thumbs_up=0, thumbs_down=0,
            )

        fb = await db.execute_fetchall(
            "SELECT SUM(thumb) AS up, SUM(1-thumb) AS down FROM feedback"
        )
        up = fb[0]["up"] or 0
        down = fb[0]["down"] or 0

        return MetricsSummary(
            total_queries=total,
            resolved=r["resolved"] or 0,
            escalated=r["escalated"] or 0,
            resolution_rate=round((r["resolved"] or 0) / total * 100, 1),
            avg_best_score=round(r["avg_score"] or 0, 4),
            thumbs_up=up,
            thumbs_down=down,
        )


@router.get("/queries", response_model=QueryHistoryResponse)
async def query_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    desde: str | None = Query(None),
    hasta: str | None = Query(None),
    escalated: bool | None = Query(None),
):
    async with await get_db() as db:
        where, params = _date_filter(desde, hasta)
        if escalated is not None:
            connector = "AND" if where else "WHERE"
            where += f" {connector} escalated = ?"
            params.append(1 if escalated else 0)

        total_row = await db.execute_fetchall(
            f"SELECT COUNT(*) AS n FROM queries {where}", params
        )
        total = total_row[0]["n"]

        offset = (page - 1) * page_size
        rows = await db.execute_fetchall(
            f"""
            SELECT ts, session_id, message, best_score, escalated, latency_ms, sources
            FROM queries {where}
            ORDER BY ts DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        )

        items = [
            QueryRecord(
                ts=r["ts"],
                session_id=r["session_id"],
                message=r["message"],
                best_score=r["best_score"],
                escalated=bool(r["escalated"]),
                latency_ms=r["latency_ms"],
                sources=[Source(**s) for s in json.loads(r["sources"])],
            )
            for r in rows
        ]

        return QueryHistoryResponse(
            total=total, page=page, page_size=page_size, items=items
        )


def _date_filter(desde: str | None, hasta: str | None) -> tuple[str, list]:
    clauses, params = [], []
    if desde:
        clauses.append("ts >= ?")
        params.append(desde)
    if hasta:
        clauses.append("ts <= ?")
        params.append(hasta + "T23:59:59")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
