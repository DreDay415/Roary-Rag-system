# ROARY — Repo-to-Reach

### From GitHub Repository to Market-Ready Content in Under 90 Seconds.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![uv](https://img.shields.io/badge/managed%20by-uv-blueviolet)](https://astral.sh/uv)
[![OpenRouter](https://img.shields.io/badge/LLM%20routing-OpenRouter-orange)](https://openrouter.ai)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)](https://fastapi.tiangolo.com)
[![CrewAI](https://img.shields.io/badge/orchestration-CrewAI-red)](https://crewai.com)

---

ROARY is a **self-hosted, agentic orchestration engine** that ingests any
public GitHub repository and autonomously produces brand-aligned content
marketing assets: LinkedIn threads, technical blog outlines, and product
battlecards.

It demonstrates enterprise-grade LLM orchestration, dual-RAG vector
architecture, cost-optimised model routing, and a fully typed FastAPI
service layer — all deployable on local hardware with a single `uv sync`.

---

## The Problem

Developer Advocates and Technical Founders spend 4–8 hours per week manually
translating technical work into social content. They read READMEs, identify
the value, find the angle, write the hook, revise the draft, and check it
against brand guidelines. For every trending tool they want to cover, that
cycle repeats.

**ROARY eliminates that cycle entirely.**

---

## How It Works

```
GitHub URL  →  Smart Crawler  →  Dual-RAG  →  4-Agent Newsroom  →  Markdown Report
               (2 API calls)     (ChromaDB)    (Lead Engineer         (saved + returned
                                 local, free)   → Marketer             via FastAPI)
                                               → Ghostwriter
                                               → Quality Critic)
```

1. **Smart Crawler** fetches repo metadata and README via the GitHub REST API.
   No git binary required for Phase 1; a shallow clone is available for
   full-corpus RAG ingestion.

2. **Dual-RAG Layer** chunks and embeds the content into a local ChromaDB
   instance using `all-MiniLM-L6-v2` — a 90 MB sentence-transformer model
   that runs fully on CPU. Zero per-query cost. Zero data leaves the machine.

3. **Four-Agent Newsroom** runs a sequential CrewAI pipeline:
   - **Lead Engineer** — extracts the tech stack, architecture, and core problem
   - **Product Marketer** — derives 3–5 value propositions for the target audience
   - **Ghostwriter** — drafts the content asset in the defined brand voice
   - **Quality Critic** — reviews for AI-slop, banned words, and factual accuracy

4. **FastAPI Service** exposes the pipeline as a REST API, ready for
   integration with Paperclip, n8n, or any HTTP client.

---

## Production Results

| Repository | Execution Time | Total Tokens | Cost (est.) | Critic Verdict |
|---|---|---|---|---|
| `pallets/flask` | 76.3s | 12,863 | ~$0.04 | **PASS** |
| `pydantic/pydantic-ai` | ~90s | ~15,000 | ~$0.05 | **PASS** |

Both reports passed the Quality Critic's five-point review on the first
iteration with no revision required.

---

## Key Features

### Strict Pydantic Typing Throughout

Every data structure that flows between agents is a **frozen Pydantic model**.
The crawler produces a `RepoData`. The API accepts a `ReportRequest` and
returns a `ReportResponse`. The `RunResult` from the crew carries the
Markdown content, file path, timing, and token counts — all typed,
all validated at the boundary.

```python
class ReportResponse(BaseModel):
    repo_name: str
    github_url: str
    generated_at: str                 # ISO 8601 UTC
    execution_time_seconds: float
    token_usage: TokenUsageResponse   # prompt / completion / cached / requests
    saved_path: str
    markdown: str
```

### Real Token Usage Metrics

ROARY pulls actual token counts from `CrewOutput.token_usage` (populated by
LiteLLM's callback layer) — not estimates. Every report includes:

```json
"token_usage": {
  "total_tokens": 12863,
  "prompt_tokens": 9554,
  "completion_tokens": 3309,
  "cached_prompt_tokens": 0,
  "successful_requests": 4
}
```

This is the portfolio presentation metric: you can show an interviewer the
exact cost of running a four-agent pipeline against a real repository.

### Anti-AI-Slop Quality Gate

The Quality Critic runs five sequential checks before any content is saved:

1. Banned word scan (`delve`, `tapestry`, `seamlessly`, `groundbreaking`, …)
2. AI-slop pattern detection (hollow openers, passive-voice overuse)
3. Factual accuracy cross-check against the Lead Engineer's technical brief
4. Per-post character count (LinkedIn's 220-character limit)
5. Brand voice alignment (direct, nerdy, accurate)

A `VERDICT: FAIL` routes the draft back to the Ghostwriter with numbered
revision notes. No human in the loop required.

### Cost-Routing via OpenRouter

```
Agents 1–3 (deep reasoning)  →  anthropic/claude-sonnet-4.5
Agent 4  (binary review)     →  anthropic/claude-3.5-haiku
```

The Quality Critic executes a structured scan — pattern matching, not creative
generation. Routing it to Haiku at roughly 1/5th the cost of Sonnet saves
~$0.01–0.02 per report while delivering identical accuracy on the review task.

All routing flows through **OpenRouter** as a single invoice point, enabling
model fallback and cost observability without touching the application code.

### Dual-RAG: Privacy-First Vector Architecture

| Collection | Lifecycle | Contents |
|---|---|---|
| `code_context` | Ephemeral — wiped per run | Target repo embeddings |
| `brand_soul` | Persistent | Brand guidelines, tone examples, prohibited words |

The ephemeral `code_context` collection ensures that analysis of repository A
never contaminates analysis of repository B. The persistent `brand_soul`
collection survives across runs, accumulating brand knowledge over time.

Local ChromaDB means **no source code leaves the machine** — a hard
requirement for enterprise and proprietary repository analysis.

---

## Cost Model

| Component | Cost |
|---|---|
| Lead Engineer (Sonnet 4.5) | ~$0.015 |
| Product Marketer (Sonnet 4.5) | ~$0.010 |
| Ghostwriter (Sonnet 4.5) | ~$0.012 |
| Quality Critic (Haiku 3.5) | ~$0.002 |
| Embeddings (`all-MiniLM-L6-v2`) | **$0.000** |
| Vector search (local ChromaDB) | **$0.000** |
| **Total per report** | **$0.03 – $0.08** |

PRD ceiling: $0.50 per report. Actual cost: **6–16% of budget consumed.**

---

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for:
- Full Mermaid.js data flow diagrams
- Dual-RAG design rationale
- Agent task sequencing and context wiring
- Agentic critique loop walkthrough
- Portability contract (macOS ↔ Ubuntu)
- Key design decisions table

---

## Quickstart

See [QUICKSTART.md](./QUICKSTART.md) for:
- `uv` installation and `uv sync`
- `.env` configuration for OpenRouter
- All four CLI modes with expected output
- FastAPI server startup + `curl` examples
- Swagger UI walkthrough
- Production deployment on Ubuntu / Dell Optiplex 3040
- Troubleshooting reference

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Package management | `uv` (lock-file based, fully reproducible) |
| Agent orchestration | CrewAI 1.12 |
| LLM routing | OpenRouter → LiteLLM |
| Models | claude-sonnet-4.5 (reasoning) / claude-3.5-haiku (review) |
| Vector store | ChromaDB (local PersistentClient) |
| Embeddings | `sentence-transformers` / `all-MiniLM-L6-v2` (CPU, free) |
| Chunking | LangChain `RecursiveCharacterTextSplitter` (language-aware) |
| Data validation | Pydantic v2 (frozen models throughout) |
| API framework | FastAPI + Uvicorn |
| Environment | `python-dotenv` |

---

## Portability

ROARY is architected for **1:1 parity** between the development environment
(macOS / MacBook Pro) and production (Ubuntu 22.04 / Dell Optiplex 3040).

`uv.lock` pins every transitive dependency — including `torch`, `chromadb`,
and `sentence-transformers` — to an exact version and hash. `uv sync` on
the Optiplex produces a byte-identical environment to the MacBook in under
60 seconds, without a Docker daemon, without a `requirements.txt`, and
without any `pip install --upgrade` surprises.

The ChromaDB data directory (`./data/chromadb/`) is a SQLite file that
survives the `rsync` to production unchanged. The `.env` file carries all
secrets. Nothing else is environment-specific.

---

## Project Status

| Phase | Status | Description |
|---|---|---|
| Phase 1 — Crawler | ✅ Complete | GitHub API ingestion, Pydantic schema |
| Phase 2 — RAG | ✅ Complete | ChromaDB, local embeddings, similarity search |
| Phase 3 — Newsroom | ✅ Complete | 4-agent crew, critique loop, Markdown output |
| Phase 4 — API | ✅ Complete | FastAPI service, Paperclip integration |
| Phase 5 — Brand Soul RAG | 🔜 Planned | Persistent brand-voice collection, `brand_context` injection |
| Phase 6 — LangGraph Cycle | 🔜 Planned | Formal FAIL → Ghostwriter retry loop with state graph |
| Phase 7 — Tracing | 🔜 Planned | LangSmith / Langfuse token cost + agent reasoning graph |

---

## License

MIT. Built for [Oceanpark Digital LLC](https://oceanparkdigital.com).
