from fastapi import APIRouter, HTTPException

from app.rag.memory import _store, clear_session
from app.schemas import SessionDeleteResponse, SessionHistoryResponse, TurnRecord

router = APIRouter(prefix="/sessions", tags=["sessions"])


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
    return SessionDeleteResponse(status="ok", session_id=session_id)
