# ROARY — System Architecture

> **Repo-to-Reach** ingests any public GitHub repository and autonomously
> produces brand-aligned content marketing assets via a four-agent LLM
> orchestration pipeline, a dual-RAG vector layer, and a cost-optimised
> model routing strategy.

---

## Table of Contents

1. [High-Level Data Flow](#1-high-level-data-flow)
2. [Module Map](#2-module-map)
3. [Phase 1 — Smart Crawler](#3-phase-1--smart-crawler)
4. [Phase 2 — Dual-RAG Architecture](#4-phase-2--dual-rag-architecture)
5. [Phase 3 — The Newsroom: Multi-Agent Factory](#5-phase-3--the-newsroom-multi-agent-factory)
6. [Phase 4 — API Layer](#6-phase-4--api-layer)
7. [Cost-Routing Strategy](#7-cost-routing-strategy)
8. [Portability Contract](#8-portability-contract)
9. [Key Design Decisions](#9-key-design-decisions)

---

## 1. High-Level Data Flow

```mermaid
flowchart TD
    A([User: GitHub URL]) --> B[Smart Crawler\nGitHub REST API / shallow clone]
    B --> C[RepoData\nPydantic Schema]
    C --> D[README Ingester\nRecursiveCharacterTextSplitter]
    D --> E[(ChromaDB\ncode_context collection)]
    C --> F[Lead Engineer Agent\nclaude-sonnet-4.5]
    F --> G[Product Marketer Agent\nclaude-sonnet-4.5]
    G --> H[Ghostwriter Agent\nclaude-sonnet-4.5]
    H --> I[Quality Critic Agent\nclaude-3.5-haiku]
    I -->|VERDICT: PASS| J[RunResult\nMarkdown + Metrics]
    I -->|VERDICT: FAIL| H
    J --> K[outputs/\nrepo_timestamp.md]
    J --> L[FastAPI\nPOST /generate-report]
    E -.->|RAG context| F

    style A fill:#1a1a2e,color:#e0e0e0
    style K fill:#16213e,color:#e0e0e0
    style L fill:#0f3460,color:#e0e0e0
    style E fill:#533483,color:#e0e0e0
```

---

## 2. Module Map

```
src/roary/
│
├── crawler/
│   ├── github.py       # fetch_repo_summary() — GitHub REST API, 2 round-trips
│   │                   # crawl()              — shallow git clone + noise filter
│   └── parser.py       # RepoData             — frozen Pydantic schema (Phase 1 output)
│
├── rag/
│   ├── chroma_db.py    # get_client(), reset_collection(), get_or_create_collection()
│   └── ingester.py     # ingest_readme(), query_readme()
│                       # ingest() for full-corpus (Phase 2)
│
├── agents/
│   ├── actors.py       # make_lead_engineer/marketer/ghostwriter/critic()
│   ├── tasks.py        # build_tasks() — wires context chain between tasks
│   └── crew.py         # build_crew(), run_report() → RunResult
│
└── api/
    └── main.py         # FastAPI app: GET /heartbeat, POST /generate-report
```

---

## 3. Phase 1 — Smart Crawler

### 3a. Lightweight Path (API-only)

`fetch_repo_summary()` makes exactly **two GitHub REST API calls**:

1. `GET /repos/{owner}/{repo}` — metadata (stars, language, topics, timestamps)
2. `GET /repos/{owner}/{repo}/readme` — base64-decoded README content

The result is validated into a **frozen** `RepoData` Pydantic model that flows
through the entire downstream pipeline as the single source of truth.

### 3b. Full-Corpus Path (Phase 2 RAG)

`crawl()` performs a `depth=1` shallow git clone into a `tempfile.mkdtemp`
directory. The tree walker applies a multi-layer noise filter before returning
any file:

```mermaid
flowchart LR
    A[All repo files] --> B{Directory in\nIGNORED_DIRS?}
    B -- yes --> Z[/drop/]
    B -- no --> C{Extension in\nIGNORED_EXTENSIONS?}
    C -- yes --> Z
    C -- no --> D{Filename in\nIGNORED_FILENAMES?}
    D -- yes --> Z
    D -- no --> E{Size > 500 KB?}
    E -- yes --> Z
    E -- no --> F{UTF-8\ndecodable?}
    F -- no --> Z
    F -- yes --> G([keep: RepoFile])
```

**Noise reduction observed in production:** 96% of raw files discarded
(27 dropped, 1 kept for `octocat/Hello-World`).

---

## 4. Phase 2 — Dual-RAG Architecture

ROARY maintains **two permanently separate ChromaDB collections** under
`./data/chromadb/`:

| Collection | Lifecycle | Purpose |
|---|---|---|
| `code_context` | **Ephemeral** — wiped on every new crawl | Embeddings of the target repository's README and source files. Isolated per run so stale vectors from a previous repo never contaminate the current analysis. |
| `brand_soul` | **Persistent** — survives across all runs | Brand guidelines, prohibited words, tone examples, and past high-performing content. The Ghostwriter queries this before drafting to enforce voice consistency. |

### Why Local ChromaDB?

1. **Privacy** — source code never leaves the machine. Enterprise clients
   with proprietary repos can use ROARY without any code reaching a cloud
   vector service.
2. **Speed** — sub-millisecond similarity search on local hardware vs.
   network round-trips to a hosted vector DB.
3. **Cost** — zero per-query fees. Embeddings use `all-MiniLM-L6-v2` via
   `sentence-transformers` — a 90 MB model that runs fully on CPU, adding
   $0.00 to the per-report cost.
4. **Portability** — `./data/chromadb/` is a SQLite file. It survives
   `uv sync` on the Ubuntu Optiplex without Docker volume mappings.

### Chunking Strategy

```python
# Language-aware splitter: prefers class → function → block → line → char
splitter = RecursiveCharacterTextSplitter.from_language(
    language=Language.MARKDOWN,   # or PYTHON, JS, GO, RUST, etc.
    chunk_size=1_000,             # ≈ 250 tokens — fits any LLM context window
    chunk_overlap=200,            # prevents function signatures from splitting
)
```

Every chunk carries metadata so agents can cite their source:

```json
{
  "source": "src/auth/middleware.py",
  "file_ext": ".py",
  "repo_name": "owner/repo",
  "chunk_index": 4
}
```

---

## 5. Phase 3 — The Newsroom: Multi-Agent Factory

### 5a. Agent Roster

```mermaid
graph LR
    LE[Lead Engineer\nclaude-sonnet-4.5\ntemp=0.3]
    PM[Product Marketer\nclaude-sonnet-4.5\ntemp=0.3]
    GW[Ghostwriter\nclaude-sonnet-4.5\ntemp=0.3]
    QC[Quality Critic\nclaude-3.5-haiku\ntemp=0.2]

    LE -->|Technical Brief| PM
    PM -->|Value Propositions| GW
    GW -->|LinkedIn Thread Draft| QC
    QC -->|VERDICT: PASS| OUT([RunResult])
    QC -->|VERDICT: FAIL + notes| GW
```

### 5b. Task Chain & Context Wiring

```mermaid
sequenceDiagram
    participant Repo as RepoData
    participant T1 as analyze_repo
    participant T2 as extract_value
    participant T3 as draft_content
    participant T4 as critique_draft
    participant Out as RunResult

    Repo->>T1: repo_name, description, readme
    T1->>T2: context=[T1]  full technical brief
    T1->>T3: context=[T1, T2]
    T2->>T3: value propositions
    T1->>T4: context=[T1, T3]  brief for fact-checking
    T3->>T4: draft thread
    T4->>Out: VERDICT: PASS + polished thread
```

Each downstream task receives the **complete output** of all upstream tasks as
context, not just a one-line summary. This is why the Quality Critic can
fact-check the Ghostwriter's thread against the Lead Engineer's brief —
it has both in its context window simultaneously.

### 5c. The Agentic Critique Loop

The Quality Critic is the anti-AI-slop firewall. It runs five checks in order:

1. **Banned word scan** — `delve`, `tapestry`, `unleash`, `leverage` (verb),
   `game-changer`, `groundbreaking`, `revolutionize`, `seamlessly`, `robust`,
   `streamline`
2. **AI-slop pattern detection** — hollow openers (`"In today's fast-paced..."`),
   passive-voice overuse, vague superlatives
3. **Factual accuracy** — every technical claim must trace back to the Lead
   Engineer's brief; unverifiable claims are flagged
4. **Character count** — each LinkedIn post must be ≤ 220 characters
5. **Brand voice** — direct, nerdy, accurate, slightly irreverent

A `VERDICT: FAIL` response routes the draft back to the Ghostwriter with
numbered revision notes (Phase 4 LangGraph cycle). In the current sequential
implementation, the Critic also applies minor touch-ups inline before
returning its final answer.

**Production results:** Both `pallets/flask` and `pydantic/pydantic-ai`
passed on the first iteration with no revision required.

### 5d. Measured Performance

| Metric | `pallets/flask` | `pydantic/pydantic-ai` |
|---|---|---|
| Execution time | 76.3s | ~90s |
| Total tokens | 12,863 | ~15,000 |
| Prompt tokens | 9,554 | — |
| Completion tokens | 3,309 | — |
| LLM requests | 4 | 4 |
| Critic verdict | PASS | PASS |
| Estimated cost | ~$0.04 | ~$0.05 |

---

## 6. Phase 4 — API Layer

```mermaid
sequenceDiagram
    participant Client as Paperclip / curl
    participant API as FastAPI (uvicorn)
    participant Crawler as Smart Crawler
    participant Crew as Newsroom Crew
    participant DB as ChromaDB

    Client->>API: GET /heartbeat
    API-->>Client: 200 { status, service, version, uptime_seconds }

    Client->>API: POST /generate-report\n{ github_url, brand_context? }
    API->>Crawler: fetch_repo_summary(github_url)
    Crawler-->>API: RepoSummary
    API->>API: validate → RepoData
    API->>Crew: run_report(repo)  [sync, thread-pool]
    Crew->>DB: reset code_context collection
    Crew->>Crew: kickoff() sequential process
    Crew-->>API: RunResult
    API-->>Client: 200 ReportResponse\n{ markdown, token_usage,\nexecution_time_seconds, saved_path }
```

**Key implementation detail:** `generate_report` is declared as a synchronous
`def` function (not `async def`). FastAPI automatically offloads synchronous
path operations to a thread-pool worker via `anyio`, keeping the event loop
free to handle `/heartbeat` probes while the ~76-second crew run executes in
the background.

---

## 7. Cost-Routing Strategy

All LLM calls are routed through **OpenRouter** (`openrouter.ai/api/v1`) using
LiteLLM's native `openrouter/` provider prefix. OpenRouter acts as a single
invoice point and enables model fallback without code changes.

```
openrouter/anthropic/claude-sonnet-4.5   →  Agents 1, 2, 3
openrouter/anthropic/claude-3.5-haiku    →  Agent 4 (Quality Critic)
```

**Why this split?**

- The Lead Engineer, Marketer, and Ghostwriter require deep reasoning over
  long context windows (full README + upstream task outputs). Sonnet 4.5
  handles this with high accuracy.
- The Quality Critic is a **binary classifier + formatter**: scan for patterns,
  emit PASS/FAIL. Haiku executes this task at 1/5th the cost of Sonnet with
  no perceptible quality difference for structured review tasks.

**Estimated cost per report: $0.03 – $0.08** — well within the PRD's $0.50
ceiling.

---

## 8. Portability Contract

ROARY is architected for **1:1 parity** between development (macOS / MacBook
Pro) and production (Ubuntu 22.04 / Dell Optiplex 3040).

```
Development                          Production
────────────────────────────────     ────────────────────────────────
macOS 14 (Darwin 24.1)               Ubuntu 22.04 LTS
Python 3.11 (via .python-version)    Python 3.11 (via .python-version)
uv 0.x                               uv 0.x
./data/chromadb/  (SQLite)           ./data/chromadb/  (SQLite)
.env              (dotenv)           .env              (dotenv / systemd)
outputs/          (local FS)         outputs/          (local FS / NFS)
```

**The portability guarantee is enforced by `uv`:**

```bash
# On the Optiplex — full environment reproduced in < 60 seconds:
git clone https://github.com/you/roary && cd roary
cp .env.example .env && vim .env   # add OPENROUTER_API_KEY
uv sync                             # resolves from uv.lock — no surprises
uv run main.py https://github.com/pallets/flask --report
```

`uv.lock` pins every transitive dependency to an exact version and hash.
`torch`, `sentence-transformers`, and `chromadb` — the three heaviest packages —
are resolved identically on both machines. No `requirements.txt` drift,
no `pip install --upgrade` surprises in production.

---

## 9. Key Design Decisions

| Decision | Rationale |
|---|---|
| **Frozen Pydantic models** (`frozen=True`) | All inter-agent data structures are immutable. Downstream agents cannot accidentally mutate upstream context. |
| **Shallow git clone** (`depth=1`) | Fetches only the latest commit tree. A `depth=1` clone of a large repo like `django` takes ~8s vs. 4+ minutes for a full history clone. |
| **`def` (sync) FastAPI endpoint** | Avoids blocking the async event loop during the ~76s crew run. FastAPI's thread-pool worker handles it transparently. |
| **Collection reset on each run** | `reset_collection()` wipes `code_context` before every ingest. Eliminates stale-vector contamination across successive repo analyses. |
| **`OPENROUTER_API_KEY` checked at agent construction** | Fails fast with a human-readable `EnvironmentError` before any LLM calls are made or tokens are spent. |
| **Real token metrics from `CrewOutput.token_usage`** | `UsageMetrics` is populated by LiteLLM's callback layer. No estimation — actual prompt/completion/cached counts per run. |
| **Metadata on every chunk** | `source`, `file_ext`, `repo_name`, `chunk_index` — agents can cite their sources precisely, not just hallucinate file names. |
