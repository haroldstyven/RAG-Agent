import asyncio
from typing import Protocol, runtime_checkable

import httpx
from google import genai

from app.config import settings

_GEMINI_CONCURRENCY = 5  # llamadas simultáneas a la API de embeddings


@runtime_checkable
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class GeminiEmbedder:
    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_embed_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        gemini-embedding-2 no soporta batch real — llamamos N veces.
        Usamos asyncio.gather + semáforo para paralelizar sin sobrepasar el rate limit.
        """
        sem = asyncio.Semaphore(_GEMINI_CONCURRENCY)

        async def _one(text: str) -> list[float]:
            async with sem:
                result = await asyncio.to_thread(
                    self._client.models.embed_content,
                    model=self._model,
                    contents=text,
                )
                return result.embeddings[0].values

        return list(await asyncio.gather(*[_one(t) for t in texts]))


class OllamaEmbedder:
    def __init__(self):
        self._base_url = settings.ollama_base_url
        self._model = settings.ollama_embed_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=60) as client:
            vectors = []
            for text in texts:
                resp = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self._model, "prompt": text},
                )
                resp.raise_for_status()
                vectors.append(resp.json()["embedding"])
            return vectors


def get_embedder() -> Embedder:
    if settings.embed_provider == "ollama":
        return OllamaEmbedder()
    return GeminiEmbedder()
