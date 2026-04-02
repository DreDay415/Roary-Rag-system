"""Chunk, embed, and store a :class:`~roary.crawler.github.CrawlResult`.

Pipeline
--------
1. For each :class:`~roary.crawler.github.RepoFile`, pick a language-aware
   ``RecursiveCharacterTextSplitter`` based on the file extension so that
   natural code boundaries (class / function definitions) are preferred split
   points over arbitrary character counts.
2. Attach metadata to every chunk: ``source``, ``file_ext``, ``repo_name``,
   and ``chunk_index`` — so downstream agents always know *where* a chunk
   came from.
3. Embed all chunks locally using ``all-MiniLM-L6-v2`` via
   ``langchain-huggingface``.  No API key required, no per-token cost.
4. Upsert into a ``langchain_chroma.Chroma`` vector store backed by a
   :class:`chromadb.PersistentClient`.

Usage::

    from roary.crawler.github import crawl
    from roary.rag.ingester import ingest

    result = ingest(crawl("https://github.com/owner/repo"))
    print(result)  # IngestResult(repo='owner/repo', chunks=142, files=18)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from roary.crawler.github import CrawlResult
from roary.crawler.parser import RepoData
from roary.rag.chroma_db import (
    CODE_CONTEXT_COLLECTION,
    DEFAULT_PERSIST_DIR,
    get_client,
    reset_collection,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------

EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
"""Sentence-transformer model used for local, cost-free embeddings.

~90 MB on first download; cached in ~/.cache/huggingface thereafter.
384-dim vectors — fast and good enough for code similarity retrieval.
"""

# ---------------------------------------------------------------------------
# Chunking settings
# ---------------------------------------------------------------------------

CHUNK_SIZE: int = 1_000
"""Maximum characters per chunk.  1 000 chars ≈ 250 tokens, well within
typical LLM context windows while keeping individual chunks focused."""

CHUNK_OVERLAP: int = 200
"""Characters of overlap between consecutive chunks.  Prevents a function
signature and its body from being split across two non-overlapping chunks."""

# Map file extensions → LangChain Language enum so the splitter uses
# language-appropriate separators (class → function → block → line → char).
_EXT_TO_LANGUAGE: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".jsx": Language.JS,
    ".ts": Language.JS,
    ".tsx": Language.JS,
    ".java": Language.JAVA,
    ".cpp": Language.CPP,
    ".cc": Language.CPP,
    ".cxx": Language.CPP,
    ".c": Language.C,
    ".go": Language.GO,
    ".rb": Language.RUBY,
    ".rs": Language.RUST,
    ".md": Language.MARKDOWN,
    ".html": Language.HTML,
    ".sol": Language.SOL,
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestResult:
    """Summary returned after a successful ingestion run."""

    collection_name: str
    repo_name: str
    files_processed: int
    chunks_added: int

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"IngestResult("
            f"repo={self.repo_name!r}, "
            f"collection={self.collection_name!r}, "
            f"files={self.files_processed}, "
            f"chunks={self.chunks_added})"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_splitter(ext: str) -> RecursiveCharacterTextSplitter:
    """Return a language-aware splitter for *ext*, or a generic one."""
    lang = _EXT_TO_LANGUAGE.get(ext.lower())
    if lang:
        return RecursiveCharacterTextSplitter.from_language(
            language=lang,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        # Generic fallback separators: paragraph → line → word → char
        separators=["\n\n", "\n", " ", ""],
    )


def _file_to_documents(
    path: str,
    content: str,
    repo_name: str,
) -> list[Document]:
    """Split one file into overlapping :class:`~langchain_core.documents.Document` chunks.

    Each chunk carries metadata so agents can cite their sources:

    * ``source``      — relative file path within the repo
    * ``file_ext``    — lowercase extension (``".py"``, ``".md"``, …)
    * ``repo_name``   — ``owner/repo`` identifier
    * ``chunk_index`` — zero-based position within this file's chunks
    """
    ext = Path(path).suffix.lower()
    splitter = _make_splitter(ext)
    chunks = splitter.split_text(content)

    return [
        Document(
            page_content=chunk,
            metadata={
                "source": path,
                "file_ext": ext if ext else "none",
                "repo_name": repo_name,
                "chunk_index": idx,
            },
        )
        for idx, chunk in enumerate(chunks)
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_embeddings(model_name: str = EMBEDDING_MODEL) -> HuggingFaceEmbeddings:
    """Construct the local embedding model.

    The model weights are downloaded once and cached in
    ``~/.cache/huggingface``.  Subsequent calls use the cache instantly.

    Args:
        model_name: Any ``sentence-transformers`` model name or local path.

    Returns:
        A :class:`~langchain_huggingface.HuggingFaceEmbeddings` instance
        ready to be passed into a ``Chroma`` vector store.
    """
    logger.info("Loading embedding model %r …", model_name)
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def ingest(
    crawl_result: CrawlResult,
    *,
    collection_name: str = CODE_CONTEXT_COLLECTION,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    embeddings: HuggingFaceEmbeddings | None = None,
    reset: bool = True,
) -> IngestResult:
    """Chunk, embed, and store every file in *crawl_result*.

    Args:
        crawl_result: Output of :func:`~roary.crawler.github.crawl`.
        collection_name: ChromaDB collection to write into.
            Defaults to :data:`~roary.rag.chroma_db.CODE_CONTEXT_COLLECTION`.
        persist_dir: Directory where ChromaDB persists data.
        embeddings: Pre-built embedding model.  Pass an existing instance to
            avoid re-loading the model weights when calling ``ingest`` multiple
            times in the same process.
        reset: When ``True`` (default) the collection is wiped before
            ingestion.  Set to ``False`` to append to an existing collection
            (e.g. for the persistent brand-soul collection).

    Returns:
        :class:`IngestResult` with counts of processed files and chunks.

    Raises:
        ValueError: If *crawl_result* contains no files.
    """
    if not crawl_result.files:
        raise ValueError(
            f"CrawlResult for {crawl_result.repo_name!r} has no files to ingest."
        )

    if embeddings is None:
        embeddings = build_embeddings()

    # Prepare the collection (wipe it clean for ephemeral code-context runs)
    client = get_client(persist_dir)
    if reset:
        reset_collection(client, collection_name)

    # Build all LangChain Documents from every file in the crawl
    all_docs: list[Document] = []
    for repo_file in crawl_result.files:
        docs = _file_to_documents(
            path=repo_file.path,
            content=repo_file.content,
            repo_name=crawl_result.repo_name,
        )
        all_docs.extend(docs)
        logger.debug(
            "%s → %d chunk(s)",
            repo_file.path,
            len(docs),
        )

    logger.info(
        "Embedding %d chunks from %d files into collection %r …",
        len(all_docs),
        len(crawl_result.files),
        collection_name,
    )

    # Upsert into ChromaDB via the LangChain wrapper
    Chroma.from_documents(
        documents=all_docs,
        embedding=embeddings,
        collection_name=collection_name,
        client=client,
    )

    logger.info(
        "Ingestion complete: %d chunks stored in %r",
        len(all_docs),
        collection_name,
    )

    return IngestResult(
        collection_name=collection_name,
        repo_name=crawl_result.repo_name,
        files_processed=len(crawl_result.files),
        chunks_added=len(all_docs),
    )


def query(
    question: str,
    *,
    collection_name: str = CODE_CONTEXT_COLLECTION,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    embeddings: HuggingFaceEmbeddings | None = None,
    k: int = 4,
) -> list[Document]:
    """Retrieve the *k* most relevant chunks for *question*.

    Convenience wrapper used by downstream agents so they never need to touch
    the Chroma client directly.

    Args:
        question: Natural-language query, e.g. ``"What does the auth module do?"``.
        collection_name: Collection to search.
        persist_dir: ChromaDB data directory.
        embeddings: Pre-built embedding model (shared with ``ingest`` calls).
        k: Number of results to return.

    Returns:
        List of :class:`~langchain_core.documents.Document` objects sorted by
        relevance (most relevant first).
    """
    if embeddings is None:
        embeddings = build_embeddings()

    client = get_client(persist_dir)
    store = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        client=client,
    )
    return store.similarity_search(question, k=k)


# ---------------------------------------------------------------------------
# README-specific helpers (Phase 1 RAG path)
# ---------------------------------------------------------------------------


def _repo_collection_name(repo_name: str) -> str:
    """Derive a valid ChromaDB collection name from an ``owner/repo`` string.

    ChromaDB requires names to be 3-63 characters, start/end with an
    alphanumeric character, and contain only ``[a-zA-Z0-9_-]``.

    Examples::

        "pallets/flask"   → "pallets_flask"
        "octocat/Hello-World" → "octocat_Hello-World"
    """
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", repo_name)
    name = name[:63].ljust(3, "_")  # enforce 3-char minimum
    return name


def ingest_readme(
    repo: RepoData,
    *,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    embeddings: HuggingFaceEmbeddings | None = None,
) -> IngestResult:
    """Chunk and embed a repository's README into its own ChromaDB collection.

    This is the Phase 1 RAG path: it takes the :class:`~roary.crawler.parser.RepoData`
    produced by :func:`~roary.crawler.github.fetch_repo_summary` — no full
    clone required.

    The collection is named after the repository (``owner_repo``) and wiped
    clean on each call so a re-run on the same URL always reflects the current
    README rather than appending stale chunks.

    Args:
        repo: Validated :class:`~roary.crawler.parser.RepoData` from Phase 1.
        persist_dir: ChromaDB data directory (default ``./data/chromadb``).
        embeddings: Pre-built embedding model; constructed if ``None``.

    Returns:
        :class:`IngestResult` with chunk count.

    Raises:
        ValueError: If the README is empty.
    """
    if not repo.readme.strip():
        raise ValueError(f"README for {repo.repo_name!r} is empty — nothing to ingest.")

    if embeddings is None:
        embeddings = build_embeddings()

    collection_name = _repo_collection_name(repo.repo_name)

    # Markdown-aware splitter keeps section headings with their content
    splitter = RecursiveCharacterTextSplitter.from_language(
        language=Language.MARKDOWN,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = splitter.split_text(repo.readme)

    docs = [
        Document(
            page_content=chunk,
            metadata={
                "source": "README.md",
                "file_ext": ".md",
                "repo_name": repo.repo_name,
                "chunk_index": idx,
            },
        )
        for idx, chunk in enumerate(chunks)
    ]

    client = get_client(persist_dir)
    reset_collection(client, collection_name)

    Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        collection_name=collection_name,
        client=client,
    )

    logger.info(
        "README ingested: %d chunks → collection %r",
        len(docs),
        collection_name,
    )

    return IngestResult(
        collection_name=collection_name,
        repo_name=repo.repo_name,
        files_processed=1,
        chunks_added=len(docs),
    )


def query_readme(
    question: str,
    repo_name: str,
    *,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    embeddings: HuggingFaceEmbeddings | None = None,
    k: int = 3,
) -> list[Document]:
    """Search the README collection for *question*.

    Args:
        question: Natural-language query.
        repo_name: ``owner/repo`` identifier used to derive the collection name.
        persist_dir: ChromaDB data directory.
        embeddings: Pre-built embedding model; constructed if ``None``.
        k: Number of top results to return.

    Returns:
        Up to *k* :class:`~langchain_core.documents.Document` objects,
        most relevant first.
    """
    return query(
        question,
        collection_name=_repo_collection_name(repo_name),
        persist_dir=persist_dir,
        embeddings=embeddings,
        k=k,
    )
