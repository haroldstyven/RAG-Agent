"""
Cross-encoder reranker usando sentence-transformers.
Se carga una sola vez en RAM (singleton).
Activar con USE_RERANKER=true en .env
"""
from __future__ import annotations

_instance = None


def get_reranker():
    global _instance
    if _instance is None:
        from sentence_transformers import CrossEncoder
        _instance = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _instance
