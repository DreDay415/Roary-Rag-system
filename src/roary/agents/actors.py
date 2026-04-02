"""CrewAI agent definitions for ROARY's 'Newsroom' multi-agent pipeline.

Four agents, each with a distinct specialisation and cost-optimised model:

+-----------------------+-------------------------------+--------------------------------+
| Agent                 | Responsibility                | Model                          |
+=======================+===============================+================================+
| Lead Engineer         | Technical analysis of the     | claude-3.5-sonnet (OpenRouter) |
|                       | repository — stack, purpose,  | (deep code reasoning)          |
|                       | and core logic extraction.    |                                |
+-----------------------+-------------------------------+--------------------------------+
| Product Marketer      | Translate the technical brief | claude-3.5-sonnet (OpenRouter) |
|                       | into market-facing value      |                                |
|                       | propositions.                 |                                |
+-----------------------+-------------------------------+--------------------------------+
| Ghostwriter           | Draft the final content asset | claude-3.5-sonnet (OpenRouter) |
|                       | (LinkedIn thread, blog post)  |                                |
|                       | in the correct brand voice.   |                                |
+-----------------------+-------------------------------+--------------------------------+
| Quality Critic        | Review for AI-slop, banned    | claude-3-haiku (OpenRouter)    |
|                       | words, and brand alignment.   | (fast, cheap gatekeeper)       |
|                       | Returns PASS or FAIL + notes. |                                |
+-----------------------+-------------------------------+--------------------------------+

All LLM calls are routed through OpenRouter (https://openrouter.ai/api/v1).
The ``OPENROUTER_API_KEY`` env var must be set — loaded automatically from
``.env`` via python-dotenv.  No key → :class:`EnvironmentError` at
construction time.
"""

from __future__ import annotations

import os

from crewai import Agent
from crewai.llm import LLM
from dotenv import load_dotenv

# Load .env before anything reads os.environ — must happen at import time
# so OPENROUTER_API_KEY is visible to LiteLLM when it initialises the LLM.
load_dotenv()

# ---------------------------------------------------------------------------
# Model constants  (change here to reroute the whole crew)
# ---------------------------------------------------------------------------

# claude-3.5-sonnet routes to Bedrock on this account and fails.
# claude-sonnet-4.5 and claude-3.5-haiku both route via Anthropic's direct API.
_SONNET: str = "openrouter/anthropic/claude-sonnet-4.5"
_HAIKU: str = "openrouter/anthropic/claude-3.5-haiku"


def _require_api_key() -> None:
    """Raise early with a clear message if the OpenRouter key is missing."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set. "
            "Add it to your .env file or export it before running the crew:\n"
            "  export OPENROUTER_API_KEY=sk-or-..."
        )


# ---------------------------------------------------------------------------
# LLM instances (one per tier — shared across agents of the same tier)
# ---------------------------------------------------------------------------


def _sonnet_llm() -> LLM:
    # LiteLLM's native openrouter/ routing: strips the prefix and calls
    # https://openrouter.ai/api/v1 automatically using OPENROUTER_API_KEY.
    # Passing base_url alongside the prefix caused a double-routing conflict.
    return LLM(model=_SONNET, temperature=0.3)


def _haiku_llm() -> LLM:
    return LLM(model=_HAIKU, temperature=0.2)


# ---------------------------------------------------------------------------
# Agent factories
# ---------------------------------------------------------------------------


def make_lead_engineer() -> Agent:
    """The Lead Engineer — deep technical analysis of the target repository.

    Reads the repository metadata and README, identifies the tech stack from
    manifest files (``package.json``, ``requirements.txt``, ``go.mod``, …),
    locates core logic, and produces a structured technical brief that the
    downstream agents build upon.
    """
    _require_api_key()
    return Agent(
        role="Lead Engineer",
        goal=(
            "Analyse the GitHub repository thoroughly. "
            "Identify the programming language(s) and framework(s) used, "
            "extract the core architectural patterns, and summarise what "
            "problem the tool solves and how it solves it technically."
        ),
        backstory=(
            "You are a senior software engineer with 15 years of experience "
            "across multiple stacks. You can read a README and a handful of "
            "source files and instantly understand what a project does, how it "
            "is structured, and why its design decisions were made. Your output "
            "is always precise, technical, and free of marketing language."
        ),
        llm=_sonnet_llm(),
        verbose=True,
        allow_delegation=False,
    )


def make_product_marketer() -> Agent:
    """The Product Marketer — converts technical facts into market value.

    Receives the Lead Engineer's technical brief and translates it into
    concrete, audience-facing value propositions: what pain it solves, who
    benefits, and why it matters now.
    """
    _require_api_key()
    return Agent(
        role="Product Marketer",
        goal=(
            "Transform the Lead Engineer's technical brief into 3–5 compelling "
            "value propositions aimed at Developer Advocates and Technical Founders. "
            "Focus on the 'so what?' — the business impact and developer productivity "
            "gains, not the implementation details."
        ),
        backstory=(
            "You are a former software engineer turned product marketer. You speak "
            "both languages fluently: you understand how things work under the hood, "
            "and you know how to articulate why that matters to a technical buyer. "
            "You despise vague buzzwords and always back claims with specifics."
        ),
        llm=_sonnet_llm(),
        verbose=True,
        allow_delegation=False,
    )


def make_ghostwriter() -> Agent:
    """The Ghostwriter — crafts the final content asset.

    Takes the value propositions and drafts a polished LinkedIn thread (or
    other requested format) in the brand voice.  Must not sound like AI.
    """
    _require_api_key()
    return Agent(
        role="Ghostwriter",
        goal=(
            "Write a compelling LinkedIn thread (5–8 posts) that introduces the "
            "repository to a technical audience. The thread must be conversational, "
            "specific, and punchy — never vague or generic. "
            "Absolutely forbidden words: 'delve', 'tapestry', 'unleash', 'leverage' "
            "(as a verb), 'game-changer', 'groundbreaking', 'revolutionize', "
            "'seamlessly', 'robust', 'streamline'."
        ),
        backstory=(
            "You are a ghostwriter for technical founders and developer advocates "
            "with an audience of 50 000+ followers. Your threads get shared because "
            "they teach something concrete in under two minutes. You have internalized "
            "the brand voice: direct, nerdy, a little irreverent, always accurate. "
            "You treat AI-generated filler phrases the way a surgeon treats infection — "
            "cut them out immediately."
        ),
        llm=_sonnet_llm(),
        verbose=True,
        allow_delegation=False,
    )


def make_quality_critic() -> Agent:
    """The Quality Critic — the final gatekeeper before output is saved.

    Reviews the Ghostwriter's draft against the brand voice rules and the
    prohibited word list.  Returns a structured verdict: PASS or FAIL with
    specific revision notes.  In the LangGraph loop (Phase 4), a FAIL will
    route the draft back to the Ghostwriter.
    """
    _require_api_key()
    return Agent(
        role="Quality Critic",
        goal=(
            "Review the draft LinkedIn thread and return a verdict. "
            "Check for: (1) banned words — 'delve', 'tapestry', 'unleash', "
            "'leverage' as verb, 'game-changer', 'groundbreaking', 'revolutionize', "
            "'seamlessly', 'robust', 'streamline'; "
            "(2) AI-slop patterns — vague superlatives, passive voice overuse, "
            "hollow openers like 'In today's fast-paced world'; "
            "(3) factual drift — any claim not supported by the technical brief. "
            "Respond with 'VERDICT: PASS' or 'VERDICT: FAIL' followed by "
            "numbered revision notes."
        ),
        backstory=(
            "You are a brutally honest editorial director. You have seen thousands "
            "of AI-generated drafts and can spot one in the first sentence. "
            "You protect the brand by rejecting anything that sounds generic, "
            "sycophantic, or technically inaccurate. You give specific, actionable "
            "revision notes — never vague complaints."
        ),
        llm=_haiku_llm(),
        verbose=True,
        allow_delegation=False,
    )
