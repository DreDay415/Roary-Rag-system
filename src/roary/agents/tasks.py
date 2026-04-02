"""CrewAI task definitions for ROARY's Newsroom pipeline.

Task sequence
-------------
1. ``analyze_repo``     — Lead Engineer reads the repo and produces a technical brief.
2. ``extract_value``    — Product Marketer derives value propositions from the brief.
3. ``draft_content``    — Ghostwriter writes the LinkedIn thread from the propositions.
4. ``critique_draft``   — Quality Critic reviews and returns PASS / FAIL + notes.

Each task passes its full output as ``context`` to the next, so every agent
has the complete upstream reasoning available — not just a one-line summary.
"""

from __future__ import annotations

from crewai import Task

from roary.agents.actors import (
    make_lead_engineer,
    make_product_marketer,
    make_ghostwriter,
    make_quality_critic,
)
from roary.crawler.parser import RepoData


def build_tasks(
    repo: RepoData,
    lead_engineer: object,
    product_marketer: object,
    ghostwriter: object,
    quality_critic: object,
) -> list[Task]:
    """Construct the four ordered tasks, wiring context between them.

    Args:
        repo: Validated repo metadata from Phase 1; injected into task
            descriptions so agents receive the actual content, not
            instructions to go fetch it themselves.
        lead_engineer: Agent instance for task 1.
        product_marketer: Agent instance for task 2.
        ghostwriter: Agent instance for task 3.
        quality_critic: Agent instance for task 4.

    Returns:
        Ordered list of :class:`~crewai.Task` objects ready to pass to
        :class:`~crewai.Crew`.
    """
    # ── Task 1: Technical Analysis ──────────────────────────────────────────
    task_analyze = Task(
        name="analyze_repo",
        description=(
            f"Analyse the following GitHub repository and produce a structured "
            f"technical brief.\n\n"
            f"Repository : {repo.repo_name}\n"
            f"Description: {repo.description or '(none provided)'}\n\n"
            f"README content:\n"
            f"{'─' * 60}\n"
            f"{repo.readme}\n"
            f"{'─' * 60}\n\n"
            f"Your brief must cover:\n"
            f"1. Tech stack (language, frameworks, key dependencies)\n"
            f"2. Core problem the project solves\n"
            f"3. How it solves it (architectural approach, key abstractions)\n"
            f"4. Notable design decisions or trade-offs\n"
            f"5. Target audience (who would use this and why)"
        ),
        expected_output=(
            "A structured technical brief in Markdown with five clearly labelled "
            "sections matching the five points above. Be specific and technical — "
            "no marketing language."
        ),
        agent=lead_engineer,
    )

    # ── Task 2: Value Proposition Extraction ────────────────────────────────
    task_extract = Task(
        name="extract_value",
        description=(
            "You have received the Lead Engineer's technical brief (above). "
            "Translate it into 3–5 value propositions aimed at Developer Advocates "
            "and Technical Founders.\n\n"
            "For each proposition:\n"
            "- State the pain point it addresses\n"
            "- State the specific benefit (with numbers/metrics where inferable)\n"
            "- State why this project's approach is better than the status quo\n\n"
            "Avoid vague superlatives. Every claim must be anchored in the "
            "technical brief."
        ),
        expected_output=(
            "A numbered list of 3–5 value propositions, each 2–4 sentences. "
            "Format: '**VP N: [Title]** — [pain] → [benefit] → [differentiation]'."
        ),
        agent=product_marketer,
        context=[task_analyze],
    )

    # ── Task 3: Content Draft ────────────────────────────────────────────────
    task_draft = Task(
        name="draft_content",
        description=(
            "You have the technical brief and the value propositions (above). "
            f"Write a LinkedIn thread introducing '{repo.repo_name}' to a technical "
            f"audience.\n\n"
            f"Thread structure:\n"
            f"  Post 1 (hook): One punchy sentence that makes a developer stop scrolling.\n"
            f"  Posts 2–6 (body): One value proposition or technical insight per post, "
            f"max 3 sentences each.\n"
            f"  Post 7 (CTA): A direct call to action — star the repo, read the docs, "
            f"try the quick-start.\n\n"
            f"HARD RULES:\n"
            f"  • Never use: delve, tapestry, unleash, leverage (verb), game-changer, "
            f"groundbreaking, revolutionize, seamlessly, robust, streamline\n"
            f"  • Every technical claim must trace back to the brief\n"
            f"  • Each post stands alone — assume the reader sees only that post\n"
            f"  • Write in first-person plural ('We just discovered…') or second-person "
            f"('You need to see this…') — never corporate third-person\n"
            f"  • Max 220 characters per post (LinkedIn limit)"
        ),
        expected_output=(
            "The complete LinkedIn thread as a numbered Markdown list. "
            "Each post on its own line, prefixed '**Post N:**'. "
            "No preamble, no meta-commentary — just the thread."
        ),
        agent=ghostwriter,
        context=[task_analyze, task_extract],
    )

    # ── Task 4: Quality Critique ─────────────────────────────────────────────
    task_critique = Task(
        name="critique_draft",
        description=(
            "Review the Ghostwriter's LinkedIn thread draft (above).\n\n"
            "Run the following checks in order:\n"
            "1. **Banned words**: scan every post for the forbidden list.\n"
            "2. **AI-slop patterns**: flag hollow openers, passive-voice overuse, "
            "vague superlatives, filler transitions.\n"
            "3. **Factual accuracy**: every technical claim must be supported by "
            "the Lead Engineer's brief. Flag anything unverifiable.\n"
            "4. **Character count**: flag any post exceeding 220 characters.\n"
            "5. **Brand voice**: direct, nerdy, accurate, a little irreverent.\n\n"
            "Return your verdict on the FIRST line as exactly one of:\n"
            "  VERDICT: PASS\n"
            "  VERDICT: FAIL\n"
            "Followed by numbered revision notes (empty list if PASS)."
        ),
        expected_output=(
            "First line: 'VERDICT: PASS' or 'VERDICT: FAIL'.\n"
            "If PASS: the polished final thread (incorporate any minor touch-ups "
            "directly — don't just say 'looks good').\n"
            "If FAIL: numbered list of specific revision notes the Ghostwriter "
            "must action, referencing the exact post number and offending text."
        ),
        agent=quality_critic,
        context=[task_analyze, task_draft],
    )

    return [task_analyze, task_extract, task_draft, task_critique]
