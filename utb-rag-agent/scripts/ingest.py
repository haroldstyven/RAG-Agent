"""CLI: uv run python scripts/ingest.py"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.ingest import ingest_docs


async def main():
    print("Indexando documentos en ./docs ...")
    total = await ingest_docs()
    print(f"\nListo — {total} chunks indexados en ChromaDB.")


if __name__ == "__main__":
    asyncio.run(main())
