import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import AsyncGenerator

from app.config import settings
from app.rag.llm import ESCALAR_TOKEN, get_llm
from app.rag.memory import Session, Turn, get_session, persist_turn
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

# ── Cache de respuestas frecuentes ──────────────────────────────────────────
_cache: dict[str, tuple[ChatResponse, datetime]] = {}
_CACHE_TTL = timedelta(minutes=5)
_CACHE_MAX = 200


def _cache_key(message: str) -> str:
    return hashlib.md5(message.lower().strip().encode()).hexdigest()


def _cache_get(message: str) -> ChatResponse | None:
    key = _cache_key(message)
    entry = _cache.get(key)
    if entry and datetime.now() < entry[1]:
        return entry[0]
    _cache.pop(key, None)
    return None


def _cache_set(message: str, response: ChatResponse) -> None:
    if len(_cache) >= _CACHE_MAX:
        oldest = min(_cache, key=lambda k: _cache[k][1])
        _cache.pop(oldest, None)
    _cache[_cache_key(message)] = (response, datetime.now() + _CACHE_TTL)


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


def _build_sources(
    chunks: list[RetrievedChunk],
    threshold: float,
) -> list[dict]:
    """
    Deduplica por documento (mejor distancia por doc), filtra por umbral,
    convierte distancia → similitud (1 - dist), ordena desc, max 3.
    """
    best: dict[str, RetrievedChunk] = {}
    for c in chunks:
        if c.source not in best or c.score < best[c.source].score:
            best[c.source] = c

    relevant = [c for c in best.values() if c.score < threshold]
    relevant.sort(key=lambda c: c.score)  # menor distancia primero = mayor similitud

    return [
        {
            "doc": c.source,
            "score": round(1.0 - c.score, 4),
            "snippet": c.text[:220].replace("\n", " ").strip(),
        }
        for c in relevant[:3]
    ]


# ── Respuesta completa (usada por webhook WhatsApp / email) ─────────────────

async def chat(
    message: str,
    session_id: str | None = None,
    channel: str = "web",
) -> ChatResponse:
    t0 = time.perf_counter()

    # Cache sólo para queries sin sesión activa (WhatsApp/Email canales stateless)
    if not session_id:
        cached = _cache_get(message)
        if cached:
            return cached

    session = get_session(session_id) if session_id else None
    chunks = await retrieve(message, history=_history_turns(session))
    best_score = chunks[0].score if chunks else float("inf")
    sources_out = [Source(**s) for s in _build_sources(chunks, settings.escalate_threshold)]

    if not chunks or best_score > settings.escalate_threshold:
        if session and session_id:
            session.add("user", message)
            session.add("assistant", "ESCALADO")
            asyncio.create_task(persist_turn(session_id, "user", message))
            asyncio.create_task(persist_turn(session_id, "assistant", "ESCALADO"))
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
        if session and session_id:
            session.add("user", message)
            session.add("assistant", "ESCALADO")
            asyncio.create_task(persist_turn(session_id, "user", message))
            asyncio.create_task(persist_turn(session_id, "assistant", "ESCALADO"))
        await log_query(message, best_score, True, session_id,
                        [s.model_dump() for s in sources_out],
                        latency_ms=latency_ms, channel=channel)
        return ChatResponse(answer=_ESCALATE_MSG, escalate=True, sources=sources_out)

    if session and session_id:
        session.add("user", message)
        session.add("assistant", answer)
        asyncio.create_task(persist_turn(session_id, "user", message))
        asyncio.create_task(persist_turn(session_id, "assistant", answer))
    await log_query(message, best_score, False, session_id,
                    [s.model_dump() for s in sources_out],
                    latency_ms=latency_ms, channel=channel)
    result = ChatResponse(answer=answer, escalate=False, sources=sources_out)
    if not session_id:
        _cache_set(message, result)
    return result


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
        sources_out = _build_sources(chunks, settings.escalate_threshold)

        if not chunks or best_score > settings.escalate_threshold:
            if session and session_id:
                session.add("user", message)
                session.add("assistant", "ESCALADO")
                asyncio.create_task(persist_turn(session_id, "user", message))
                asyncio.create_task(persist_turn(session_id, "assistant", "ESCALADO"))
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
            if session and session_id:
                session.add("user", message)
                session.add("assistant", "ESCALADO")
                asyncio.create_task(persist_turn(session_id, "user", message))
                asyncio.create_task(persist_turn(session_id, "assistant", "ESCALADO"))
            await log_query(message, best_score, True, session_id, sources_out,
                            latency_ms=latency_ms, channel=channel)
            yield sse({"type": "escalate", "sources": sources_out})
            return

        if session and session_id:
            session.add("user", message)
            session.add("assistant", answer)
            asyncio.create_task(persist_turn(session_id, "user", message))
            asyncio.create_task(persist_turn(session_id, "assistant", answer))
        await log_query(message, best_score, False, session_id, sources_out,
                        latency_ms=latency_ms, channel=channel)
        yield sse({"type": "done", "escalate": False, "sources": sources_out})

    except Exception as exc:
        yield sse({"type": "error", "message": str(exc)})
