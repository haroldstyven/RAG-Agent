"""
Canal WhatsApp — Meta Cloud API (Business Platform).

Flujo:
  1. Meta verifica el webhook con GET /webhook/whatsapp?hub.*
  2. Mensajes reales llegan por POST con payload JSON firmado con X-Hub-Signature-256
  3. El agente responde y enviamos el texto de vuelta con la Graph API

Variables de entorno necesarias (.env):
  WHATSAPP_VERIFY_TOKEN   — token personalizado que configuras en Meta for Developers
  WHATSAPP_APP_SECRET     — App Secret para validar la firma HMAC de cada request
  WHATSAPP_ACCESS_TOKEN   — token de acceso permanente (System User)
  WHATSAPP_PHONE_NUMBER_ID — ID del número registrado
"""
import hashlib
import hmac
import json

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.config import settings
from app.rag.agent import chat

router = APIRouter(prefix="/webhook", tags=["channels"])

_GRAPH_URL = "https://graph.facebook.com/v19.0"


# ── Verificación del webhook (Meta lo llama una sola vez al registrar) ───────

@router.get("/whatsapp")
async def whatsapp_verify(request: Request):
    params = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        return PlainTextResponse(challenge, status_code=200)

    return JSONResponse({"error": "Verificación fallida"}, status_code=403)


# ── Recepción de mensajes ────────────────────────────────────────────────────

@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    raw_body = await request.body()

    # Validar firma HMAC si el App Secret está configurado
    if settings.whatsapp_app_secret:
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_signature(raw_body, sig_header, settings.whatsapp_app_secret):
            return JSONResponse({"error": "Firma inválida"}, status_code=401)

    try:
        payload = json.loads(raw_body)
    except Exception:
        return JSONResponse({"error": "JSON inválido"}, status_code=400)

    # Meta envía pings de status (delivered, read) — ignorarlos silenciosamente
    entry = payload.get("entry", [{}])[0]
    changes = entry.get("changes", [{}])[0].get("value", {})

    # Notificaciones de estado — 200 OK sin procesar
    if "statuses" in changes and "messages" not in changes:
        return JSONResponse({"status": "ok"})

    messages = changes.get("messages", [])
    if not messages:
        return JSONResponse({"status": "ok"})

    msg = messages[0]
    msg_type = msg.get("type", "")
    sender   = msg.get("from", "")
    wa_id    = changes.get("metadata", {}).get("phone_number_id", settings.whatsapp_phone_number_id)

    # Solo procesamos texto; otros tipos reciben un aviso amable
    if msg_type == "text":
        message_text = msg["text"]["body"]
        session_id   = f"wa-{sender}"
    elif msg_type in ("image", "audio", "video", "document"):
        await _send_whatsapp(
            wa_id, sender,
            "Hola, por el momento solo puedo atender consultas de texto. "
            "Por favor, escribe tu pregunta."
        )
        return JSONResponse({"status": "unsupported_type"})
    else:
        return JSONResponse({"status": "ignored"})

    if not message_text.strip():
        return JSONResponse({"status": "empty"})

    # Llamada al agente
    response = await chat(message_text, session_id=session_id, channel="whatsapp")

    reply = response.answer
    if response.escalate:
        reply += "\n\n_Un asesor UTB continuará esta conversación._"

    await _send_whatsapp(wa_id, sender, reply)
    return JSONResponse({"status": "ok"})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, header: str, secret: str) -> bool:
    """Valida X-Hub-Signature-256: sha256=<hex>"""
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    received = header[len("sha256="):]
    return hmac.compare_digest(expected, received)


async def _send_whatsapp(phone_number_id: str, to: str, text: str) -> None:
    """Envía un mensaje de texto a través de la Meta Graph API."""
    if not settings.whatsapp_access_token:
        # Sin credenciales configuradas — solo loggear en desarrollo
        print(f"[WhatsApp→{to}] {text[:120]}")
        return

    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(
            f"{_GRAPH_URL}/{phone_number_id}/messages",
            headers={
                "Authorization": f"Bearer {settings.whatsapp_access_token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"preview_url": False, "body": text},
            },
        )
