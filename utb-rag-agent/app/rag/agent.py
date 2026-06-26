import json
import time
from typing import AsyncGenerator

from app.config import settings
from app.rag.llm import ESCALAR_TOKEN, get_llm
from app.rag.memory import Session, Turn, get_session
from app.rag.metrics import log_query
from app.rag.retriever import RetrievedChunk, retrieve
from app.schemas import ChatResponse, Source

_SYSTEM_PROMPT = """\
Eres el asistente virtual de atención al estudiante de la Universidad Tecnológica de Bolívar (UTB).

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con la información del contexto proporcionado.
2. Usa español formal, tono institucional y amable.
3. Sé conciso: máximo 2 a 4 frases directas.
4. No inventes datos, fechas, valores ni procedimientos que no estén en el contexto.
5. Si el contexto no es suficiente para responder la pregunta, responde EXACTAMENTE con el token: ESCALAR

Contexto recuperado:
{context}

{history_block}"""

_HISTORY_HEADER = "Conversación previa (solo como referencia de hilo, NO como fuente de hechos):\n{history}"

_ESCALATE_MSG = "Tu consulta será atendida por un asesor de la mesa de servicio de la UTB."


def _build_prompt(chunks: list[RetrievedChunk], session: Session | None) -> str:
    context = "\n\n---\n\n".join(f"[{c.source}]\n{c.text}" for c in chunks)
    history_block = ""
    if session:
        history = session.format_history()
        if history:
            history_block = _HISTORY_HEADER.format(history=history)
    return _SYSTEM_PROMPT.format(context=context, history_block=history_block)


def _history_turns(session: Session | None) -> list[Turn] | None:
    if session and session.turns:
        return list(session.turns)
    return None


# ── Respuesta completa (usada por webhook WhatsApp / email) ─────────────────

async def chat(
    message: str,
    session_id: str | None = None,
    channel: str = "web",
) -> ChatResponse:
    t0 = time.perf_counter()
    session = get_session(session_id) if session_id else None
    chunks = await retrieve(message, history=_history_turns(session))
    best_score = chunks[0].score if chunks else float("inf")
    sources_out = [Source(doc=c.source, score=round(c.score, 4)) for c in chunks]

    if not chunks or best_score > settings.escalate_threshold:
        if session:
            session.add("user", message)
            session.add("assistant", "ESCALADO")
        await log_query(message, best_score, True, session_id,
                        [s.model_dump() for s in sources_out],
                        latency_ms=(time.perf_counter() - t0) * 1000,
                        channel=channel)
        return ChatResponse(answer=_ESCALATE_MSG, escalate=True, sources=sources_out)

    system = _build_prompt(chunks, session)
    llm = get_llm()
    answer = await llm.generate(system_prompt=system, user_message=message)
    latency_ms = (time.perf_counter() - t0) * 1000

    if ESCALAR_TOKEN in answer.upper():
        if session:
            session.add("user", message)
            session.add("assistant", "ESCALADO")
        await log_query(message, best_score, True, session_id,
                        [s.model_dump() for s in sources_out],
                        latency_ms=latency_ms, channel=channel)
        return ChatResponse(answer=_ESCALATE_MSG, escalate=True, sources=sources_out)

    if session:
        session.add("user", message)
        session.add("assistant", answer)
    await log_query(message, best_score, False, session_id,
                    [s.model_dump() for s in sources_out],
                    latency_ms=latency_ms, channel=channel)
    return ChatResponse(answer=answer, escalate=False, sources=sources_out)


# ── Streaming SSE (usado por el frontend web) ────────────────────────────────

async def chat_stream(
    message: str,
    session_id: str | None = None,
    channel: str = "web",
) -> AsyncGenerator[str, None]:
    def sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    t0 = time.perf_counter()
    session = get_session(session_id) if session_id else None

    try:
        chunks = await retrieve(message, history=_history_turns(session))
        best_score = chunks[0].score if chunks else float("inf")
        sources_out = [{"doc": c.source, "score": round(c.score, 4)} for c in chunks]

        if not chunks or best_score > settings.escalate_threshold:
            if session:
                session.add("user", message)
                session.add("assistant", "ESCALADO")
            await log_query(message, best_score, True, session_id, sources_out,
                            latency_ms=(time.perf_counter() - t0) * 1000,
                            channel=channel)
            yield sse({"type": "escalate", "sources": sources_out})
            return

        system = _build_prompt(chunks, session)
        llm = get_llm()
        full_answer: list[str] = []

        async for token in llm.stream(system_prompt=system, user_message=message):
            full_answer.append(token)
            yield sse({"type": "token", "text": token})

        answer = "".join(full_answer).strip()
        latency_ms = (time.perf_counter() - t0) * 1000

        if ESCALAR_TOKEN in answer.upper():
            if session:
                session.add("user", message)
                session.add("assistant", "ESCALADO")
            await log_query(message, best_score, True, session_id, sources_out,
                            latency_ms=latency_ms, channel=channel)
            yield sse({"type": "escalate", "sources": sources_out})
            return

        if session:
            session.add("user", message)
            session.add("assistant", answer)
        await log_query(message, best_score, False, session_id, sources_out,
                        latency_ms=latency_ms, channel=channel)
        yield sse({"type": "done", "escalate": False, "sources": sources_out})

    except Exception as exc:
        yield sse({"type": "error", "message": str(exc)})
