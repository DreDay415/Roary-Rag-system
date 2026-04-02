"""ChromaDB client factory for ROARY's dual-RAG architecture.

Two collections are defined by the PRD:

* **code_context** — ephemeral, wiped between crawl runs.
  Holds chunks from the currently analysed GitHub repository.

* **brand_soul** — persistent across runs.
  Holds brand guidelines, prohibited words, and past high-performing content.

Usage::

    from roary.rag.chroma_db import get_client, reset_collection

    client = get_client()                          # PersistentClient at ./data/chromadb/
    col = reset_collection(client, CODE_CONTEXT_COLLECTION)   # fresh every run
"""

from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Well-known names — import these everywhere instead of raw strings
# ---------------------------------------------------------------------------

DEFAULT_PERSIST_DIR: str = "./data/chromadb"
"""Default directory (relative to CWD) where ChromaDB persists its data."""

CODE_CONTEXT_COLLECTION: str = "code_context"
"""Ephemeral collection: reset before each new repository is ingested."""

BRAND_SOUL_COLLECTION: str = "brand_soul"
"""Persistent collection: brand voice, guidelines, and prohibited words."""


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def get_client(
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
) -> chromadb.PersistentClient:
    """Return a :class:`chromadb.PersistentClient` backed by *persist_dir*.

    Creates the directory if it does not already exist.  Telemetry is
    disabled so no data is sent to Chroma's servers.

    Args:
        persist_dir: Path (relative or absolute) where ChromaDB stores its
            SQLite database and embedding index.

    Returns:
        A configured, ready-to-use ``PersistentClient``.
    """
    path = Path(persist_dir)
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(path),
        settings=Settings(anonymized_telemetry=False),
    )
    logger.debug("ChromaDB client ready at %s", path.resolve())
    return client


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------


def reset_collection(
    client: chromadb.PersistentClient,
    name: str,
) -> chromadb.Collection:
    """Delete *name* if it exists, then create a fresh empty collection.

    Use this for the ephemeral **code_context** collection so every crawl
    starts with a clean slate instead of accumulating stale embeddings from
    previous repositories.

    Args:
        client: A connected ``PersistentClient``.
        name: Collection name to wipe and recreate.

    Returns:
        The newly created (empty) :class:`chromadb.Collection`.
    """
    existing_names = {c.name for c in client.list_collections()}
    if name in existing_names:
        client.delete_collection(name)
        logger.info("Dropped existing collection %r", name)
    collection = client.create_collection(name)
    logger.info("Created fresh collection %r", name)
    return collection


def get_or_create_collection(
    client: chromadb.PersistentClient,
    name: str,
) -> chromadb.Collection:
    """Return *name*, creating it if absent.

    Use this for the persistent **brand_soul** collection where content must
    survive across multiple pipeline runs.

    Args:
        client: A connected ``PersistentClient``.
        name: Collection name to open or create.

    Returns:
        The existing or newly created :class:`chromadb.Collection`.
    """
    collection = client.get_or_create_collection(name)
    logger.debug("Using collection %r (%d docs)", name, collection.count())
    return collection
