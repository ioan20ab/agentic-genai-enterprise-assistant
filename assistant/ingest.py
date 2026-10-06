"""Load enterprise documents (Markdown, text, PDF), chunk them and build the vector index.

    python -m assistant.ingest [--docs data/sample_docs] [--chunk-size 800]
"""
from __future__ import annotations

import argparse
import re
from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import Settings, get_settings
from .providers import get_embeddings

SUPPORTED = {".md", ".txt", ".pdf"}


def load_documents(docs_dir: Path) -> list[Document]:
    docs = []
    for path in sorted(docs_dir.rglob("*")):
        if path.suffix.lower() not in SUPPORTED:
            continue
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            for i, page in enumerate(PdfReader(path).pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    docs.append(Document(page_content=text, metadata={"source": path.name, "page": i}))
        else:
            text = path.read_text(encoding="utf-8")
            title = re.search(r"^#\s+(.+)$", text, re.M)
            docs.append(Document(page_content=text, metadata={
                "source": path.name, "title": title.group(1).strip() if title else path.stem}))
    return docs


def chunk_documents(docs: list[Document], settings: Settings) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " "],
    )
    chunks = splitter.split_documents(docs)
    for i, c in enumerate(chunks):
        c.metadata["chunk_id"] = i
    return chunks


def build_index(settings: Settings | None = None) -> InMemoryVectorStore:
    settings = settings or get_settings()
    docs = load_documents(settings.docs_dir)
    if not docs:
        raise FileNotFoundError(f"No .md/.txt/.pdf documents found in {settings.docs_dir}")
    store = InMemoryVectorStore(get_embeddings(settings))
    store.add_documents(chunk_documents(docs, settings))
    settings.index_path.parent.mkdir(parents=True, exist_ok=True)
    store.dump(str(settings.index_path))
    get_store.cache_clear()
    return store


@lru_cache(maxsize=1)
def get_store() -> InMemoryVectorStore:
    """Load the persisted index, building it on first use."""
    settings = get_settings()
    if not settings.index_path.exists():
        return build_index(settings)
    return InMemoryVectorStore.load(str(settings.index_path), get_embeddings(settings))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docs", type=Path)
    ap.add_argument("--chunk-size", type=int)
    args = ap.parse_args()
    import os

    if args.docs:
        os.environ["DOCS_DIR"] = str(args.docs)
    if args.chunk_size:
        os.environ["CHUNK_SIZE"] = str(args.chunk_size)
    store = build_index()
    print(f"Indexed {len(store.store)} chunks -> {get_settings().index_path}")


if __name__ == "__main__":
    main()
