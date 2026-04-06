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
            f"Write a 250–400 word executive brief introducing '{repo.repo_name}' "
            f"to a busy CTO or Technical Founder.\n\n"
            f"STRUCTURE (required):\n"
            f"  ## [One-line punchy headline about what the repo does]\n"
            f"  **The Problem** — one short paragraph on the pain this solves.\n"
            f"  **What It Does** — 2–4 bullets, each anchored to a concrete fact "
            f"from the Lead Engineer's brief.\n"
            f"  **Why It Matters** — one short paragraph answering 'So What?' for "
            f"a technical decision-maker.\n"
            f"  **Get Started** — one line CTA (star, read docs, run the quick-start).\n\n"
            f"READABILITY RULES (all mandatory):\n"
            f"  • Target 250–400 words total — count before submitting\n"
            f"  • 8th-grade reading level: short sentences, active voice, no jargon\n"
            f"  • Bold the single most important insight in each section\n"
            f"  • Every paragraph must answer 'So what?' — if it doesn't, cut it\n"
            f"  • Write in second-person ('You get…', 'Your team can…')\n\n"
            f"BANNED WORDS (zero tolerance):\n"
            f"  delve, tapestry, unleash, leverage (verb), game-changer, game changer,\n"
            f"  groundbreaking, revolutionize, seamlessly, robust, streamline,\n"
            f"  unlocking excellence, in today's world, transforming the landscape\n\n"
            f"REPOSITORY URL (mandatory):\n"
            f"  The final content line of the brief MUST be the repository URL on its\n"
            f"  own line, preceded by a blank line, exactly as written:\n"
            f"  {repo.github_url}"
        ),
        expected_output=(
            "A 250–400 word executive brief in Markdown with five clearly labelled "
            "sections: headline, The Problem, What It Does, Why It Matters, Get Started. "
            f"The second-to-last content line must be a blank line followed by the "
            f"repository URL '{repo.github_url}' on its own line. "
            "No preamble, no meta-commentary. Word count must appear on the very last "
            "line as: '<!-- words: N -->'"
        ),
        agent=ghostwriter,
        context=[task_analyze, task_extract],
    )

    # ── Task 4: Quality Critique ─────────────────────────────────────────────
    task_critique = Task(
        name="critique_draft",
        description=(
            "Review the Ghostwriter's executive brief (above).\n\n"
            "Run the following checks in order:\n"
            "1. **Banned words**: scan every sentence. Forbidden: delve, tapestry, "
            "unleash, leverage (verb), game-changer, game changer, groundbreaking, "
            "revolutionize, seamlessly, robust, streamline, unlocking excellence, "
            "in today's world, transforming the landscape.\n"
            "2. **AI-slop patterns**: flag hollow openers, passive-voice overuse, "
            "vague superlatives, paragraphs that don't answer 'So What?'\n"
            "3. **Readability**: flag if word count is outside 250–400 words, "
            "if required sections (headline, The Problem, What It Does, Why It Matters, "
            "Get Started) are missing, or if any paragraph exceeds 3 sentences.\n"
            "4. **Factual accuracy**: every claim must trace to the Lead Engineer's "
            "brief. Flag anything unverifiable.\n"
            "5. **Brand voice**: second-person, 8th-grade level, active voice.\n"
            f"6. **Repository URL**: the brief MUST contain the repository URL "
            f"'{repo.github_url}' on its own line immediately before the word-count "
            f"comment. If the URL is missing or incorrect, that is an automatic "
            f"VERDICT: FAIL — add a revision note instructing the Ghostwriter to "
            f"append it.\n\n"
            "Return your verdict on the FIRST line as exactly one of:\n"
            "  VERDICT: PASS\n"
            "  VERDICT: FAIL\n"
            "Followed by numbered revision notes (empty list if PASS)."
        ),
        expected_output=(
            "First line: 'VERDICT: PASS' or 'VERDICT: FAIL'.\n"
            "If PASS: the polished final brief with any minor touch-ups applied "
            "directly — do not just say 'looks good', output the complete brief.\n"
            "If FAIL: numbered list of specific revision notes referencing the exact "
            "section and offending text."
        ),
        agent=quality_critic,
        context=[task_analyze, task_draft],
    )

    return [task_analyze, task_extract, task_draft, task_critique]
