"""Assembles and runs ROARY's four-agent Newsroom crew.

Public API
----------
* :func:`build_crew`   — construct the :class:`~crewai.Crew` (useful for
  inspection or testing without kicking off LLM calls).
* :func:`run_report`   — end-to-end: build crew, kick it off, save the output
  Markdown file, and return a :class:`RunResult` with timing + token metrics.

The crew uses CrewAI's default **sequential process** which mirrors the
PRD's pipeline:

    Lead Engineer → Product Marketer → Ghostwriter → Quality Critic

In Phase 4 this will be upgraded to a LangGraph cycle where a FAIL verdict
from the Critic loops back to the Ghostwriter.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Vercel sets VERCEL=1 automatically in all serverless environments.
# When true, redirect all disk writes to /tmp (the only writable directory).
_ON_VERCEL: bool = bool(os.getenv("VERCEL"))

from crewai import Crew, Process

from roary.agents.actors import (
    make_ghostwriter,
    make_lead_engineer,
    make_product_marketer,
    make_quality_critic,
)
from roary.agents.tasks import build_tasks
from roary.crawler.parser import RepoData

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR: str = "outputs"


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenUsage:
    """Real token counts from CrewAI's UsageMetrics, or zeros if unavailable."""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_prompt_tokens: int = 0
    successful_requests: int = 0

    @classmethod
    def from_crew_output(cls, result: object) -> "TokenUsage":
        """Extract token counts from a :class:`~crewai.crews.crew_output.CrewOutput`."""
        usage = getattr(result, "token_usage", None)
        if usage is None:
            return cls()
        return cls(
            total_tokens=getattr(usage, "total_tokens", 0),
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
            cached_prompt_tokens=getattr(usage, "cached_prompt_tokens", 0),
            successful_requests=getattr(usage, "successful_requests", 0),
        )


@dataclass(frozen=True)
class RunResult:
    """Everything produced by a single :func:`run_report` call."""

    repo_name: str
    markdown: str
    """Full Markdown content (header + all four agent outputs)."""

    saved_path: Path
    execution_time_seconds: float
    generated_at: str
    """ISO 8601 UTC timestamp."""

    # Per-agent raw outputs (empty string if task did not run)
    engineer_output: str = ""
    marketer_output: str = ""
    ghostwriter_output: str = ""
    critic_output: str = ""

    token_usage: TokenUsage = field(default_factory=TokenUsage)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"RunResult(repo={self.repo_name!r}, "
            f"time={self.execution_time_seconds:.1f}s, "
            f"tokens={self.token_usage.total_tokens:,})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_filename(repo_name: str) -> str:
    """Convert ``owner/repo`` to a filesystem-safe filename stem."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", repo_name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_crew(repo: RepoData, *, verbose: bool = True) -> Crew:
    """Construct the Newsroom crew for *repo* without running it.

    Args:
        repo: Validated :class:`~roary.crawler.parser.RepoData` from Phase 1.
        verbose: When ``True``, agents print their reasoning to stdout.

    Returns:
        A fully configured :class:`~crewai.Crew` ready for ``.kickoff()``.
    """
    lead_engineer = make_lead_engineer()
    product_marketer = make_product_marketer()
    ghostwriter = make_ghostwriter()
    quality_critic = make_quality_critic()

    tasks = build_tasks(
        repo=repo,
        lead_engineer=lead_engineer,
        product_marketer=product_marketer,
        ghostwriter=ghostwriter,
        quality_critic=quality_critic,
    )

    return Crew(
        agents=[lead_engineer, product_marketer, ghostwriter, quality_critic],
        tasks=tasks,
        process=Process.sequential,
        verbose=verbose,
    )


def run_report(
    repo: RepoData,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    verbose: bool = True,
) -> RunResult:
    """Run the full four-agent crew and save the output as a Markdown file.

    The output filename encodes the repo name and a UTC timestamp so multiple
    runs against the same repo never overwrite each other::

        outputs/pallets_flask_20260402T143012Z.md

    Args:
        repo: Validated :class:`~roary.crawler.parser.RepoData`.
        output_dir: Directory to save the Markdown report (created if absent).
        verbose: Forward to :func:`build_crew`.

    Returns:
        :class:`RunResult` with the Markdown content, saved path, execution
        timing, and real token usage from CrewAI.

    Raises:
        EnvironmentError: If ``OPENROUTER_API_KEY`` is not set (raised by the
            agent factories before any LLM calls are made).
    """
    # On Vercel only /tmp is writable; redirect there transparently.
    output_path = Path("/tmp") if _ON_VERCEL else Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    crew = build_crew(repo, verbose=verbose)

    logger.info("Kicking off Newsroom crew for %r …", repo.repo_name)
    t0 = time.monotonic()
    result = crew.kickoff()
    elapsed = round(time.monotonic() - t0, 2)

    final_text: str = result.raw if hasattr(result, "raw") else str(result)
    token_usage = TokenUsage.from_crew_output(result)

    # Extract per-agent outputs (tasks_output is ordered: engineer, marketer, ghostwriter, critic)
    tasks_output = getattr(result, "tasks_output", [])

    def _task_raw(index: int) -> str:
        if index < len(tasks_output):
            task = tasks_output[index]
            return getattr(task, "raw", "") or ""
        return ""

    engineer_output = _task_raw(0)
    marketer_output = _task_raw(1)
    ghostwriter_output = _task_raw(2)
    critic_output = _task_raw(3)

    logger.info(
        "tasks_output counts — engineer:%d marketer:%d ghostwriter:%d critic:%d",
        len(engineer_output),
        len(marketer_output),
        len(ghostwriter_output),
        len(critic_output),
    )

    now = datetime.now(timezone.utc)
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")

    stem = _safe_filename(repo.repo_name)
    md_path = output_path / f"{stem}_{timestamp}.md"

    md_content = (
        f"# ROARY Report — {repo.repo_name}\n\n"
        f"**Generated:** {now.strftime('%Y-%m-%d %H:%M UTC')}  \n"
        f"**Repository:** <https://github.com/{repo.repo_name}>  \n"
        f"**Description:** {repo.description or '(none)'}  \n"
        f"**Execution time:** {elapsed}s  \n"
        f"**Tokens used:** {token_usage.total_tokens:,} "
        f"(prompt: {token_usage.prompt_tokens:,} / "
        f"completion: {token_usage.completion_tokens:,} / "
        f"cached: {token_usage.cached_prompt_tokens:,})  \n\n"
        f"---\n\n"
        f"## Lead Engineer — Technical Brief\n\n{engineer_output}\n\n"
        f"---\n\n"
        f"## Product Marketer — Value Propositions\n\n{marketer_output}\n\n"
        f"---\n\n"
        f"## Ghostwriter — LinkedIn Thread Draft\n\n{ghostwriter_output}\n\n"
        f"---\n\n"
        f"## Quality Critic — Final Review\n\n{critic_output}\n"
    )

    md_path.write_text(md_content, encoding="utf-8")
    logger.info(
        "Report saved → %s  [%.1fs, %d tokens]",
        md_path,
        elapsed,
        token_usage.total_tokens,
    )

    return RunResult(
        repo_name=repo.repo_name,
        markdown=md_content,
        saved_path=md_path,
        execution_time_seconds=elapsed,
        generated_at=generated_at,
        engineer_output=engineer_output,
        marketer_output=marketer_output,
        ghostwriter_output=ghostwriter_output,
        critic_output=critic_output,
        token_usage=token_usage,
    )
