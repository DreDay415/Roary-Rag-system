"""Pydantic schemas for validated crawler output.

``RepoData`` is the canonical typed envelope that flows between the crawler
and every downstream agent.  By keeping the schema in its own module, agents
can import it without pulling in the git/HTTP machinery of ``github.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RepoData(BaseModel):
    """Validated, strongly-typed snapshot of a GitHub repository.

    Populated by :func:`~roary.crawler.github.fetch_repo_summary` and passed
    to the Lead Engineer agent as its primary input.
    """

    repo_name: str = Field(
        ...,
        description="Canonical 'owner/repo' identifier, e.g. 'tiangolo/fastapi'.",
        examples=["octocat/Hello-World"],
    )
    description: str | None = Field(
        default=None,
        description="Repository description as set by the owner. None when blank.",
        examples=["My first repository on GitHub!"],
    )
    readme: str = Field(
        ...,
        description="Full decoded text of the repository README (Markdown).",
        examples=["# Hello World\n\nWelcome to the project.\n"],
    )

    model_config = {"frozen": True}
