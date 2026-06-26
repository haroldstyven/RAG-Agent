"""
Stub de webhook para WhatsApp Business.

Formato de entrada: payload genérico BSP (compatible con Meta Cloud API, Twilio, Atom).
Para conectar un proveedor real, implementa los TODO marcados abajo.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.rag.agent import chat

router = APIRouter(prefix="/webhook", tags=["channels"])


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Se requiere un payload JSON válido en el body."},
            status_code=400,
        )

    # TODO: validar firma HMAC del proveedor (Meta: X-Hub-Signature-256 | Twilio: X-Twilio-Signature)
    # TODO: para Meta Cloud API, responder el challenge de verificación GET /webhook?hub.mode=subscribe

    # ── Extracción del mensaje entrante ─────────────────────────────────────
    # Meta Cloud API
    try:
        entry = payload["entry"][0]["changes"][0]["value"]
        message_text = entry["messages"][0]["text"]["body"]
        sender = entry["messages"][0]["from"]
        # TODO: extraer también media (audio/imagen) cuando aplique
    except (KeyError, IndexError):
        # Formato alternativo Twilio / Atom
        message_text = payload.get("Body") or payload.get("message", "")
        sender = payload.get("From") or payload.get("from", "unknown")

    if not message_text:
        return JSONResponse({"status": "ignored"}, status_code=200)

    # ── Llamada al agente ────────────────────────────────────────────────────
    response = await chat(message_text)

    # ── Formato de respuesta ─────────────────────────────────────────────────
    # TODO: aquí enchufas el cliente del BSP para enviar el mensaje de vuelta:
    #   - Meta Cloud API: POST https://graph.facebook.com/v19.0/{phone_number_id}/messages
    #   - Twilio: POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json
    #   - Atom: POST {atom_base_url}/v1/messages/send

    reply_text = response.answer
    if response.escalate:
        reply_text += "\n\n_Transfiriendo con un asesor UTB..._"

    return JSONResponse(
        {
            "to": sender,
            "text": reply_text,
            "escalate": response.escalate,
            "sources": [s.model_dump() for s in response.sources],
            # TODO: remover 'sources' en producción si el BSP no lo necesita
        }
    )
