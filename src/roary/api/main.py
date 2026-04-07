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
