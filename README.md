# ROARY — Repo-to-Reach

### From GitHub Repository to Market-Ready Content in Under 90 Seconds.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![uv](https://img.shields.io/badge/managed%20by-uv-blueviolet)](https://astral.sh/uv)
[![OpenRouter](https://img.shields.io/badge/LLM%20routing-OpenRouter-orange)](https://openrouter.ai)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)](https://fastapi.tiangolo.com)
[![CrewAI](https://img.shields.io/badge/orchestration-CrewAI-red)](https://crewai.com)
[![Next.js](https://img.shields.io/badge/dashboard-Next.js%2016-black)](https://nextjs.org)
[![Cost](https://img.shields.io/badge/cost%20per%20report-~%240.04-brightgreen)]()

---

ROARY is a **self-hosted, agentic orchestration engine** that ingests any
public GitHub repository and autonomously produces brand-aligned executive
briefs and content marketing assets in under 90 seconds.

It ships with a production-grade **Next.js dashboard** featuring glassmorphism
UI, per-agent tabbed output, real-time skeleton loading, USD cost estimation,
and one-click ZIP bundle export — all backed by a FastAPI service, dual-RAG
vector architecture, and a four-agent CrewAI Newsroom.

Deployable on local hardware with a single `uv sync`. Cost per report: **~$0.04**.

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

5. **Next.js Dashboard** renders the four agent outputs in a tabbed glassmorphism
   UI with skeleton loading, cost display, and one-click `.md` / `.zip` export.

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

### Production Next.js Dashboard

The `frontend/` directory contains a full **Next.js 16 / React 19 / Tailwind v4**
dashboard — no template, built from scratch:

| Feature | Detail |
|---|---|
| **Glassmorphism hero input** | Dark charcoal + neon-blue accent, blur backdrop |
| **Multi-agent tabs** | Summary · Lead Engineer · Product Marketer · Ghostwriter |
| **Skeleton loading UI** | 5 pulsing cards matching the 5 Ghostwriter sections — shown while agents run |
| **USD Cost Estimator** | Green pill in the meta bar: blended Sonnet/Haiku pricing per run |
| **Copy-to-clipboard** | Per-tab copy button with 2-second confirmation flash |
| **Download Report (.md)** | Full combined report as a Markdown file |
| **Download Bundle (.zip)** | 5-file ZIP: one `.md` per agent + `full_report.md` |
| **Process Feed** | Timestamped sidebar log of every pipeline state change |

Run it: `cd frontend && npm run dev` (requires backend on `localhost:8000`).

---

### USD Cost Estimator

Every completed report displays a live **estimated cost** in the meta bar,
calculated from real token counts using blended model pricing:

| Model | Input | Output | Used by |
|---|---|---|---|
| `claude-sonnet-4.5` | $3.00 / 1M | $15.00 / 1M | Lead Engineer, Marketer, Ghostwriter |
| `claude-3.5-haiku` | $0.25 / 1M | $1.25 / 1M | Quality Critic |

Blended average (75% Sonnet / 25% Haiku): ~$2.31/1M input, ~$11.56/1M output.
Typical cost: **$0.03 – $0.06 per report** — displayed as `$0.04` in the UI.

Token counts come from `CrewOutput.token_usage` (LiteLLM callbacks) — actual
billed tokens, not estimates.

---

### JSON History Vault

Every completed report is **automatically persisted** to `data/history/` as a
structured JSON file:

```
data/history/
  pallets_flask_20260403T142301Z.json
  pydantic_pydantic_ai_20260403T153812Z.json
```

Each file contains the full payload: `repo_name`, `github_url`, `generated_at`,
`execution_time_seconds`, `token_usage`, `saved_path`, and all four agent outputs
(`engineer_output`, `marketer_output`, `ghostwriter_output`, `critic_output`).

The directory is created automatically on first run and excluded from git
(`.gitignore`). Use it for cost auditing, output diffing, and regression testing.

---

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
| **Frontend framework** | **Next.js 16.2.2 / React 19 / TypeScript** |
| **UI styling** | **Tailwind CSS v4 — glassmorphism dark theme** |
| **Markdown rendering** | **react-markdown + remark-gfm** |
| **ZIP export** | **JSZip** |
| **History persistence** | **JSON vault → `data/history/`** |

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
| Phase 5 — Dashboard | ✅ Complete | Next.js 16 UI — tabs, skeleton UI, cost pill, ZIP export, history vault |
| Phase 6 — Brand Soul RAG | 🔜 Planned | Persistent brand-voice collection, `brand_context` injection |
| Phase 7 — LangGraph Cycle | 🔜 Planned | Formal FAIL → Ghostwriter retry loop with state graph |
| Phase 8 — Tracing | 🔜 Planned | LangSmith / Langfuse token cost + agent reasoning graph |

---

## License

MIT. Built for [Oceanpark Digital LLC](https://oceanparkdigital.com).
