from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # Providers
    llm_provider: str = Field("gemini", pattern="^(gemini|ollama)$")
    embed_provider: str = Field("gemini", pattern="^(gemini|ollama)$")

    # Gemini
    gemini_api_key: str = ""
    gemini_llm_model: str = "gemini-2.5-flash"
    gemini_embed_model: str = "text-embedding-004"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "gemma3:4b"
    ollama_embed_model: str = "nomic-embed-text"

    # RAG — rutas relativas se resuelven desde la raíz del proyecto
    chroma_path: str = str(_PROJECT_ROOT / "data" / "chroma")
    collection_name: str = "utb_docs"
    top_k: int = 4
    escalate_threshold: float = 0.50
    chunk_size: int = 500
    chunk_overlap: int = 50
    use_reranker: bool = False  # activar con USE_RERANKER=true en .env

    # WhatsApp — Meta Cloud API
    whatsapp_verify_token: str = ""      # token personalizado para verificar el webhook
    whatsapp_app_secret: str = ""        # App Secret para validar firma HMAC
    whatsapp_access_token: str = ""      # token de acceso permanente
    whatsapp_phone_number_id: str = ""   # ID del número de teléfono en Meta

    # SendGrid — canal email
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "agente@utb.edu.co"
    sendgrid_support_email: str = "soporte@utb.edu.co"

    @field_validator("chroma_path")
    @classmethod
    def resolve_chroma_path(cls, v: str) -> str:
        p = Path(v)
        return str(p if p.is_absolute() else _PROJECT_ROOT / p)


settings = Settings()
