from fastapi import APIRouter, HTTPException, Query

from app.rag.memory import _store, clear_session
from app.schemas import (
    SessionDeleteResponse,
    SessionHistoryResponse,
    SessionListResponse,
    SessionSummary,
    TurnRecord,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, description="Filtrar por session_id"),
):
    items = list(_store.items())
    if search:
        q = search.lower()
        items = [(sid, s) for sid, s in items if q in sid.lower()]
    items.sort(key=lambda x: x[1].updated_at, reverse=True)
    total = len(items)
    return SessionListResponse(
        total=total,
        sessions=[
            SessionSummary(
                session_id=sid,
                turn_count=len(sess.turns),
                created_at=sess.created_at,
                updated_at=sess.updated_at,
                last_message=sess.last_user_message(),
            )
            for sid, sess in items[:limit]
        ],
    )


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
async def session_history(session_id: str):
    session = _store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Sesión '{session_id}' no encontrada.")
    turns = [TurnRecord(role=t.role, content=t.content) for t in session.turns]
    return SessionHistoryResponse(session_id=session_id, turns=turns)


@router.delete("/{session_id}", response_model=SessionDeleteResponse)
async def delete_session(session_id: str):
    if session_id not in _store:
        raise HTTPException(status_code=404, detail=f"Sesión '{session_id}' no encontrada.")
    clear_session(session_id)
    from app.db.database import get_db
    async with get_db() as db:
        await db.execute("DELETE FROM session_turns WHERE session_id = ?", (session_id,))
        await db.commit()
    return SessionDeleteResponse(status="ok", session_id=session_id)
