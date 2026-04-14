"""ROARY FastAPI application — Phase 4 API layer.

Endpoints
---------
GET  /heartbeat          Liveness probe for Paperclip / orchestrators.
POST /generate-report    Run the full four-agent Newsroom crew and return
                         the Markdown report as JSON.

Run locally
-----------
    uv run main.py --server                  # default host/port
    uv run main.py --server --port 9000      # custom port
    uvicorn roary.api.main:app --reload      # dev mode with auto-reload
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Vercel sets VERCEL=1 automatically at runtime.
# History writes are skipped there — /tmp is ephemeral and the payload
# is already returned in the JSON response.
_ON_VERCEL: bool = bool(os.getenv("VERCEL"))
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl

from roary.agents.crew import run_report
from roary.crawler.github import fetch_repo_summary
from roary.crawler.parser import RepoData

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ROARY Newsroom API",
    description=(
        "Autonomous multi-agent GitHub content repurposer. "
        "Feed it a public repo URL — get back a production-ready "
        "LinkedIn thread, reviewed by a Quality Critic."
    ),
    version="0.4.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ReportRequest(BaseModel):
    """Input payload for ``POST /generate-report``."""

    github_url: str = Field(
        ...,
        description="Full public GitHub repository URL.",
        examples=["https://github.com/pallets/flask"],
    )
    brand_context: str | None = Field(
        default=None,
        description=(
            "Optional brand voice context injected into the Ghostwriter's "
            "prompt (e.g. company name, tone notes, prohibited words). "
            "Reserved for Phase 4 Brand Soul RAG integration."
        ),
        examples=["Oceanpark Digital LLC — technical, direct, no buzzwords."],
    )
    output_dir: str = Field(
        default="outputs",
        description="Server-side directory to persist the Markdown file.",
    )

    model_config = {"json_schema_extra": {"example": {
        "github_url": "https://github.com/pydantic/pydantic-ai",
        "brand_context": None,
        "output_dir": "outputs",
    }}}


class TokenUsageResponse(BaseModel):
    """Token consumption breakdown from CrewAI's UsageMetrics."""

    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    cached_prompt_tokens: int
    successful_requests: int


class ReportResponse(BaseModel):
    """Output payload returned by ``POST /generate-report``."""

    repo_name: str = Field(description="Canonical 'owner/repo' identifier.")
    github_url: str = Field(description="The URL that was analysed.")
    generated_at: str = Field(description="ISO 8601 UTC timestamp.")
    execution_time_seconds: float = Field(
        description="Wall-clock seconds from crew kickoff to file save."
    )
    token_usage: TokenUsageResponse = Field(
        description="Real token counts from CrewAI — use for cost estimation."
    )
    saved_path: str = Field(description="Absolute path of the persisted .md file.")
    markdown: str = Field(description="Full Markdown content of the report (all four agents).")
    engineer_output: str = Field(description="Lead Engineer's raw technical brief.")
    marketer_output: str = Field(description="Product Marketer's raw value propositions.")
    ghostwriter_output: str = Field(description="Ghostwriter's raw LinkedIn thread draft.")
    critic_output: str = Field(description="Quality Critic's raw verdict + final thread.")


class HeartbeatResponse(BaseModel):
    """Liveness probe response."""

    status: str
    service: str
    version: str
    uptime_seconds: float


# ---------------------------------------------------------------------------
# Uptime tracking
# ---------------------------------------------------------------------------

_START_TIME: float = time.monotonic()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get(
    "/heartbeat",
    response_model=HeartbeatResponse,
    summary="Liveness probe",
    tags=["ops"],
)
async def heartbeat() -> dict[str, Any]:
    """Return service health status.

    Used by Paperclip to verify this 'employee' is alive and responsive
    before dispatching a report generation job.
    """
    return {
        "status": "healthy",
        "service": "roary-newsroom",
        "version": app.version,
        "uptime_seconds": round(time.monotonic() - _START_TIME, 1),
    }


@app.get(
    "/history",
    response_model=list[dict[str, Any]],
    summary="List all generated items (reports and chats) from local history",
    tags=["newsroom"],
)
async def list_history() -> list[dict[str, Any]]:
    """Return a unified list of metadata for all reports and chats."""
    if _ON_VERCEL:
        return []
    
    items = []
    
    # Check reports
    history_dir = Path("data/history")
    if history_dir.exists():
        for path in history_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items.append({
                        "id": path.name,
                        "type": "report",
                        "repo_name": data.get("repo_name"),
                        "title": f"Report: {data.get('repo_name')}",
                        "github_url": data.get("github_url"),
                        "generated_at": data.get("generated_at"),
                        "mtime": os.path.getmtime(path)
                    })
            except Exception:
                continue

    # Check chats
    chat_dir = Path("data/chats")
    if chat_dir.exists():
        for path in chat_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items.append({
                        "id": path.name,
                        "type": "chat",
                        "repo_name": data.get("repo_name"),
                        "title": f"Q: {data.get('question')[:30]}...",
                        "github_url": data.get("github_url"),
                        "generated_at": data.get("generated_at"),
                        "mtime": os.path.getmtime(path)
                    })
            except Exception:
                continue
    
    # Sort by mtime (most recent first)
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


@app.get(
    "/history/{filename}",
    response_model=dict[str, Any],
    summary="Get a specific item from history",
    tags=["newsroom"],
)
async def get_history_detail(filename: str) -> dict[str, Any]:
    """Return the full detail for a specific JSON file in history."""
    if _ON_VERCEL:
        raise HTTPException(status_code=404, detail="History not available on Vercel")
        
    # Check multiple locations
    paths = [Path("data/history") / filename, Path("data/chats") / filename]
    history_path = next((p for p in paths if p.exists()), None)
    
    if not history_path:
        raise HTTPException(status_code=404, detail="Item not found")
        
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Add type if missing
            if "type" not in data:
                data["type"] = "report" if "data/history" in str(history_path) else "chat"
            return data
    except Exception as exc:
        logger.exception("Failed to read history file %s", filename)
        raise HTTPException(status_code=500, detail=f"Read failure: {exc}")


class QueryRequest(BaseModel):
    """Input payload for ``POST /query``."""

    github_url: str = Field(..., description="The repository to query against.")
    question: str = Field(..., description="The user's question.")


class QueryResponse(BaseModel):
    """Output payload for ``POST /query``."""

    repo_name: str
    question: str
    answer: str
    sources: list[str]
    generated_at: str


@app.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question about the repository using RAG",
    tags=["chat"],
)
def query_repo(request: QueryRequest) -> dict[str, Any]:
    """Search the repository README using RAG and answer the user's question."""
    from roary.rag.ingester import build_embeddings, ingest_readme, query_readme
    from langchain_anthropic import ChatAnthropic
    from langchain_core.prompts import ChatPromptTemplate
    
    # ── 1. Fetch/Crawl ──────────────────────────────────────────────────────
    try:
        summary = fetch_repo_summary(request.github_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    repo = RepoData(
        repo_name=summary.full_name,
        github_url=summary.url,
        description=summary.description,
        readme=summary.readme_content,
    )

    # ── 2. Vector Search ────────────────────────────────────────────────────
    try:
        embeddings = build_embeddings()
        ingest_readme(repo, embeddings=embeddings)
        hits = query_readme(request.question, repo.repo_name, embeddings=embeddings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RAG Error: {exc}")

    if not hits:
        answer = "I couldn't find any relevant information in the README to answer that question."
        sources = []
    else:
        # ── 3. LLM Synthesis ────────────────────────────────────────────────
        context = "\n\n".join([doc.page_content for doc in hits])
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are Roary, a helpful AI lead engineer. Answer the user's question using ONLY the provided README context. If the answer isn't in the context, say so. Be direct and technical."),
            ("user", "Context from {repo_name} README:\n{context}\n\nQuestion: {question}")
        ])
        
        # We'll use Haiku for quick, cheap chat responses
        llm = ChatAnthropic(model="claude-3-5-haiku-20241022")
        chain = prompt | llm
        
        try:
            ai_msg = chain.invoke({
                "repo_name": repo.repo_name,
                "context": context,
                "question": request.question
            })
            answer = str(ai_msg.content)
            sources = [doc.metadata.get("chunk_index", "v") for doc in hits]
        except Exception as exc:
            logger.error("LLM Chat failed: %s", exc)
            answer = f"I found some relevant parts of the README, but I couldn't generate a summary. Error: {exc}"
            sources = []

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    # ── 4. Persist Chat History ─────────────────────────────────────────────
    if not _ON_VERCEL:
        chat_dir = Path("data/chats")
        chat_dir.mkdir(parents=True, exist_ok=True)
        # Using a similar naming convention to reports
        chat_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", repo.repo_name)
        chat_ts = generated_at.replace(":", "").replace("-", "")
        chat_path = chat_dir / f"chat_{chat_stem}_{chat_ts}.json"
        
        chat_payload = {
            "type": "chat",
            "repo_name": repo.repo_name,
            "github_url": request.github_url,
            "question": request.question,
            "answer": answer,
            "sources": sources,
            "generated_at": generated_at
        }
        chat_path.write_text(json.dumps(chat_payload, indent=2), encoding="utf-8")

    return {
        "repo_name": repo.repo_name,
        "question": request.question,
        "answer": answer,
        "sources": sources,
        "generated_at": generated_at
    }


@app.post(
    "/generate-report",
    response_model=ReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a content report from a GitHub repository",
    tags=["newsroom"],
)
def generate_report(request: ReportRequest) -> dict[str, Any]:
    # NOTE: sync def (not async) — FastAPI automatically offloads sync path
    # operations to a thread-pool worker, keeping the event loop free for
    # heartbeat checks while the crew (which is fully synchronous) runs.
    """Run the full four-agent Newsroom crew against a public GitHub repo.

    Pipeline
    --------
    1. Fetch repo metadata + README via the GitHub REST API.
    2. Validate into a ``RepoData`` Pydantic model.
    3. Kick off the sequential CrewAI crew:
       Lead Engineer → Product Marketer → Ghostwriter → Quality Critic.
    4. Save the Markdown report to ``output_dir``.
    5. Return the full report + execution metrics as JSON.

    Errors
    ------
    - ``422`` — Pydantic validation failure on the request body.
    - ``400`` — GitHub URL could not be parsed or repo is private/missing.
    - ``503`` — API key missing or crew execution failed.
    """
    # ── 1. Crawl ─────────────────────────────────────────────────────────────
    try:
        summary = fetch_repo_summary(request.github_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid GitHub URL: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not fetch repository: {exc}",
        ) from exc

    repo = RepoData(
        repo_name=summary.full_name,
        github_url=summary.url,
        description=summary.description,
        readme=summary.readme_content,
    )

    # ── 2. Run crew ───────────────────────────────────────────────────────────
    logger.info("API request: generating report for %r", repo.repo_name)
    try:
        run_result = run_report(
            repo,
            output_dir=request.output_dir,
            verbose=False,       # suppress agent stdout chatter in API mode
        )
    except EnvironmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Crew execution failed for %s", repo.repo_name)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Crew execution failed: {exc}",
        ) from exc

    # ── 3. Persist JSON history entry (local only) ───────────────────────────
    # Skipped on Vercel: the filesystem is read-only outside /tmp and the
    # full payload is already returned in the JSON response below.
    if not _ON_VERCEL:
        history_dir = Path("data/history")
        history_dir.mkdir(parents=True, exist_ok=True)
        history_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", run_result.repo_name)
        history_ts = run_result.generated_at.replace(":", "").replace("-", "")
        history_path = history_dir / f"{history_stem}_{history_ts}.json"
        history_payload: dict[str, Any] = {
            "repo_name": run_result.repo_name,
            "github_url": request.github_url,
            "generated_at": run_result.generated_at,
            "execution_time_seconds": run_result.execution_time_seconds,
            "token_usage": {
                "total_tokens": run_result.token_usage.total_tokens,
                "prompt_tokens": run_result.token_usage.prompt_tokens,
                "completion_tokens": run_result.token_usage.completion_tokens,
                "cached_prompt_tokens": run_result.token_usage.cached_prompt_tokens,
                "successful_requests": run_result.token_usage.successful_requests,
            },
            "saved_path": str(run_result.saved_path.resolve()),
            "engineer_output": run_result.engineer_output,
            "marketer_output": run_result.marketer_output,
            "ghostwriter_output": run_result.ghostwriter_output,
            "critic_output": run_result.critic_output,
        }
        history_path.write_text(json.dumps(history_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("History entry saved → %s", history_path)
    else:
        logger.info("Vercel runtime detected — history write skipped (payload returned in response)")

    # ── 4. Build response ────────────────────────────────────────────────────
    return {
        "repo_name": run_result.repo_name,
        "github_url": request.github_url,
        "generated_at": run_result.generated_at,
        "execution_time_seconds": run_result.execution_time_seconds,
        "token_usage": {
            "total_tokens": run_result.token_usage.total_tokens,
            "prompt_tokens": run_result.token_usage.prompt_tokens,
            "completion_tokens": run_result.token_usage.completion_tokens,
            "cached_prompt_tokens": run_result.token_usage.cached_prompt_tokens,
            "successful_requests": run_result.token_usage.successful_requests,
        },
        "saved_path": str(run_result.saved_path.resolve()),
        "markdown": run_result.markdown,
        "engineer_output": run_result.engineer_output,
        "marketer_output": run_result.marketer_output,
        "ghostwriter_output": run_result.ghostwriter_output,
        "critic_output": run_result.critic_output,
    }
