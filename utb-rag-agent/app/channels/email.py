"""
Canal email — SendGrid Inbound Parse webhook.

Configuración en SendGrid:
  1. Verificar dominio (Settings → Sender Authentication)
  2. Settings → Inbound Parse → Add Host & URL
     Host: utb.edu.co (o subdominio)
     URL:  https://tu-servidor/webhook/email

Variables de entorno necesarias (.env):
  SENDGRID_API_KEY        — para enviar la respuesta
  SENDGRID_FROM_EMAIL     — remitente del agente (debe estar verificado)
  SENDGRID_SUPPORT_EMAIL  — correo de soporte UTB (CC en escalamientos)
"""
import email as email_lib
import re

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.rag.agent import chat

router = APIRouter(prefix="/webhook", tags=["channels"])

_SENDGRID_SEND_URL = "https://api.sendgrid.com/v3/mail/send"


@router.post("/email")
async def email_webhook(request: Request):
    """
    SendGrid Inbound Parse envía los datos como multipart/form-data.
    Campos relevantes: from, to, subject, text, html, envelope.
    """
    form = await request.form()

    from_addr = str(form.get("from", ""))
    subject   = str(form.get("subject", "(sin asunto)"))
    text_body = str(form.get("text", ""))
    html_body = str(form.get("html", ""))

    # Extraer dirección de email limpia de "Nombre <email@dom.com>"
    sender_email = _extract_email(from_addr) or from_addr

    # Preferir texto plano; si no hay, limpiar HTML
    body = text_body.strip() if text_body.strip() else _strip_html(html_body)

    if not body:
        return JSONResponse({"status": "empty"})

    session_id = f"email-{sender_email}"
    response = await chat(body, session_id=session_id, channel="email")

    reply_text = response.answer
    if response.escalate:
        reply_text += (
            "\n\nNota: Tu consulta ha sido derivada a un asesor de la mesa de servicio UTB, "
            "quien te contactará a la brevedad."
        )

    await _send_email_reply(
        to=sender_email,
        subject=f"Re: {subject}",
        body=reply_text,
        cc_support=response.escalate,
    )

    return JSONResponse({"status": "ok", "escalated": response.escalate})


async def _send_email_reply(
    to: str,
    subject: str,
    body: str,
    cc_support: bool = False,
) -> None:
    """Envía la respuesta del agente vía SendGrid Mail Send API."""
    if not settings.sendgrid_api_key:
        print(f"[Email→{to}] {body[:120]}")
        return

    personalizations: dict = {"to": [{"email": to}]}
    if cc_support and settings.sendgrid_support_email:
        personalizations["cc"] = [{"email": settings.sendgrid_support_email}]

    payload = {
        "personalizations": [personalizations],
        "from": {"email": settings.sendgrid_from_email, "name": "Asistente UTB"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": body},
            {"type": "text/html",  "value": body.replace("\n", "<br>")},
        ],
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _SENDGRID_SEND_URL,
            headers={
                "Authorization": f"Bearer {settings.sendgrid_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if resp.status_code not in (200, 202):
            print(f"[email] SendGrid error {resp.status_code}: {resp.text[:200]}")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_email(addr: str) -> str | None:
    m = re.search(r"<([^>]+)>", addr)
    return m.group(1) if m else None


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).strip()
