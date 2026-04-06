"""Vercel Serverless entrypoint for the ROARY FastAPI application.

How it works
------------
Vercel's Python runtime automatically routes all requests whose path matches
``/api`` or ``/api/*`` to this file.  FastAPI's router, however, sees the
*full* incoming path (e.g. ``/api/generate-report``), so we mount the main
app at ``/api`` via a sub-application mount.  This strips the prefix before
handing off to the router, so every route defined in ``roary.api.main``
(``/heartbeat``, ``/generate-report``, …) continues to work unchanged.

PYTHONPATH
----------
``src/`` is inserted at ``sys.path[0]`` so that ``from roary.xxx import …``
resolves correctly when Vercel runs this file from the repo root without
installing the package.

Dependency note
---------------
The Vercel Python runtime has a **250 MB package limit**.  This file and
``api/requirements.txt`` deliberately exclude:

  * torch / transformers / safetensors  (~2.5 GB — WILL BUST the limit)
  * sentence-transformers               (~90 MB model + torch dependency)
  * langchain-huggingface               (requires sentence-transformers)
  * langchain-chroma / chromadb         (requires onnxruntime ~180 MB)

These are only used by ``src/roary/rag/ingester.py`` which is **not** in the
``/generate-report`` call path.  The live API endpoint relies solely on
the GitHub REST crawler and the CrewAI agent stack.

If you ever need the RAG layer in production, migrate to a hosted embedding
provider (e.g. OpenAI ``text-embedding-3-small``) and a hosted vector DB
(e.g. Upstash Vector, Pinecone, or MongoDB Atlas Vector Search).
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# PYTHONPATH fix — makes `from roary.xxx import …` work when Vercel runs
# this file directly from the project root without installing the package.
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# ---------------------------------------------------------------------------
# Import the real FastAPI app and re-expose it mounted at /api.
# ---------------------------------------------------------------------------
from fastapi import FastAPI  # noqa: E402
from roary.api.main import app as _roary_app  # noqa: E402

# Vercel routes /api/* to this file; the real app defines routes without that
# prefix.  Mounting at /api strips it before the router runs, so
# POST /api/generate-report → POST /generate-report inside _roary_app.
app = FastAPI(
    title="ROARY Newsroom API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
app.mount("/api", _roary_app)
