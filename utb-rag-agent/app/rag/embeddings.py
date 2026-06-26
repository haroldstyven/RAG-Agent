import asyncio
from typing import Protocol, runtime_checkable

import httpx
from google import genai
from google.genai import types as gtypes

from app.config import settings

_GEMINI_CONCURRENCY = 5


@runtime_checkable
class Embedder(Protocol):
    async def embed(self, texts: list[str], task_type: str | None = None) -> list[list[float]]: ...


class GeminiEmbedder:
    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_embed_model
        # task_type sólo disponible en text-embedding-004 y modelos posteriores
        self._supports_task_type = "embedding-004" in self._model or "text-embedding" in self._model

    async def embed(self, texts: list[str], task_type: str | None = None) -> list[list[float]]:
        sem = asyncio.Semaphore(_GEMINI_CONCURRENCY)

        async def _one(text: str) -> list[float]:
            async with sem:
                kwargs: dict = dict(model=self._model, contents=text)
                if task_type and self._supports_task_type:
                    kwargs["config"] = gtypes.EmbedContentConfig(task_type=task_type)
                result = await asyncio.to_thread(
                    self._client.models.embed_content,
                    **kwargs,
                )
                return result.embeddings[0].values

        return list(await asyncio.gather(*[_one(t) for t in texts]))


class OllamaEmbedder:
    def __init__(self):
        self._base_url = settings.ollama_base_url
        self._model = settings.ollama_embed_model

    def _apply_prefix(self, text: str, task_type: str | None) -> str:
        # multilingual-e5 requiere prefijos "passage:" / "query:"
        if task_type and "e5" in self._model.lower():
            prefix = "passage: " if "DOCUMENT" in task_type else "query: "
            return prefix + text
        return text

    async def embed(self, texts: list[str], task_type: str | None = None) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=60) as client:
            vectors = []
            for text in texts:
                body = self._apply_prefix(text, task_type)
                resp = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self._model, "prompt": body},
                )
                resp.raise_for_status()
                vectors.append(resp.json()["embedding"])
            return vectors


def get_embedder() -> Embedder:
    if settings.embed_provider == "ollama":
        return OllamaEmbedder()
    return GeminiEmbedder()
