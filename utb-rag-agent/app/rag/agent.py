from app.config import settings
from app.rag.llm import ESCALAR_TOKEN, get_llm
from app.rag.memory import Session, get_session
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


async def chat(message: str, session_id: str | None = None) -> ChatResponse:
    session: Session | None = get_session(session_id) if session_id else None

    chunks: list[RetrievedChunk] = await retrieve(message)
    best_score = chunks[0].score if chunks else float("inf")

    # Guardrail capa 1: sin contexto relevante → escalar
    if not chunks or best_score > settings.escalate_threshold:
        if session:
            session.add("user", message)
            session.add("assistant", "ESCALADO")
        sources_out = [Source(doc=c.source, score=round(c.score, 4)) for c in chunks]
        log_query(message, best_score, True, session_id, [s.model_dump() for s in sources_out])
        return ChatResponse(
            answer="Tu consulta será atendida por un asesor de la mesa de servicio de la UTB.",
            escalate=True,
            sources=sources_out,
        )

    context = "\n\n---\n\n".join(f"[{c.source}]\n{c.text}" for c in chunks)

    history_block = ""
    if session:
        history = session.format_history()
        if history:
            history_block = _HISTORY_HEADER.format(history=history)

    system = _SYSTEM_PROMPT.format(context=context, history_block=history_block)

    llm = get_llm()
    answer = await llm.generate(system_prompt=system, user_message=message)

    sources_out = [Source(doc=c.source, score=round(c.score, 4)) for c in chunks]

    # Guardrail capa 2: el LLM decidió escalar
    if ESCALAR_TOKEN in answer.upper():
        if session:
            session.add("user", message)
            session.add("assistant", "ESCALADO")
        log_query(message, best_score, True, session_id, [s.model_dump() for s in sources_out])
        return ChatResponse(
            answer="Tu consulta será atendida por un asesor de la mesa de servicio de la UTB.",
            escalate=True,
            sources=sources_out,
        )

    if session:
        session.add("user", message)
        session.add("assistant", answer)

    log_query(message, best_score, False, session_id, [s.model_dump() for s in sources_out])
    return ChatResponse(answer=answer, escalate=False, sources=sources_out)
