from typing import Protocol, runtime_checkable

import httpx
from google import genai
from google.genai import types

from app.config import settings

ESCALAR_TOKEN = "ESCALAR"


@runtime_checkable
class LLM(Protocol):
    async def generate(self, system_prompt: str, user_message: str) -> str: ...


class GeminiLLM:
    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_llm_model

    async def generate(self, system_prompt: str, user_message: str) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
                max_output_tokens=512,
            ),
        )
        return response.text.strip()


class OllamaLLM:
    def __init__(self):
        self._base_url = settings.ollama_base_url
        self._model = settings.ollama_llm_model

    async def generate(self, system_prompt: str, user_message: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "options": {"temperature": 0.2},
                },
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()


def get_llm() -> LLM:
    if settings.llm_provider == "ollama":
        return OllamaLLM()
    return GeminiLLM()
