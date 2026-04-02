# ROARY — Quickstart Guide

> Get from a fresh clone to a published-quality LinkedIn thread in under
> five minutes. This guide covers environment setup, the CLI, the FastAPI
> server, and the Swagger UI.

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | ≥ 3.11 | [python.org](https://python.org) |
| `uv` | any | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Git | any | pre-installed on macOS / Ubuntu |
| OpenRouter account | — | [openrouter.ai](https://openrouter.ai) — free tier available |

---

## 1. Clone & Install

```bash
git clone https://github.com/you/roary.git
cd roary

# uv reads .python-version (3.11) and creates .venv automatically
uv sync
```

`uv sync` resolves all dependencies from `uv.lock` — including `torch`,
`sentence-transformers`, and `chromadb`. On a first run expect ~2 minutes
for downloads; subsequent syncs complete in under 5 seconds.

---

## 2. Configure Environment

```bash
cp .env.example .env
```

Open `.env` and set your OpenRouter API key:

```dotenv
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Obtain a key at **openrouter.ai → Keys → Create Key**.
The free tier is sufficient for all four CLI modes.

> **Never commit `.env` to version control.** It is listed in `.gitignore`.

**Optional — GitHub token (removes the 60 req/hr unauthenticated rate limit):**

```dotenv
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
```

---

## 3. Verify Installation

```bash
# Should print the RepoData struct for a tiny public repo
uv run main.py https://github.com/octocat/Hello-World
```

Expected output:
```
┌─ ROARY — Phase 1 Ingestion Result ──────────────────────────────────────
│  repo_name  : octocat/Hello-World
│  description: My first repository on GitHub!
│  readme_len : 13 chars
│
│  README preview:
│    Hello World!
└──────────────────────────────────────────────────────────────────────────
```

---

## 4. CLI Reference

### Phase 1 — Fetch & Inspect

```bash
# Human-readable summary
uv run main.py https://github.com/pallets/flask

# Raw JSON (pipe-friendly)
uv run main.py https://github.com/pallets/flask --json

# With verbose INFO logging
uv run main.py https://github.com/pallets/flask -v
```

### Phase 2 — README RAG Search

Embeds the README into a local ChromaDB collection and runs a
similarity search. The embedding model (`all-MiniLM-L6-v2`) is
downloaded once (~90 MB) and cached in `~/.cache/huggingface`.

```bash
uv run main.py https://github.com/pallets/flask \
  --query "How does Flask handle request routing?"
```

Expected output:
```
┌─ ROARY — README Vector Search ──────────────────────────────────────────
│  repo  : pallets/flask
│  query : 'How does Flask handle request routing?'
│  hits  : 3
│
│  ── Hit 1  [chunk 0] ─────────────────────────────────────────────────────
│    Flask is a lightweight [WSGI] web application framework...
│
└──────────────────────────────────────────────────────────────────────────
```

### Phase 3 — Full Newsroom Report

Runs the four-agent CrewAI pipeline and saves a Markdown report.
**Requires `OPENROUTER_API_KEY` in `.env`.**
Typical duration: 60–120 seconds.

```bash
uv run main.py https://github.com/pydantic/pydantic-ai --report
```

Output is saved to `outputs/pydantic_pydantic-ai_<timestamp>.md` and the
terminal prints an execution summary:

```
┌─ ROARY — Report Generated ──────────────────────────────────────────────
│  repo             : pydantic/pydantic-ai
│  saved            : outputs/pydantic_pydantic-ai_20260402T202426Z.md
│  execution time   : 76.3s
│  tokens total     : 12,863
│  tokens prompt    : 9,554
│  tokens completion: 3,309
│  tokens cached    : 0
│  LLM requests     : 4
└──────────────────────────────────────────────────────────────────────────
```

Save to a custom directory:
```bash
uv run main.py https://github.com/pallets/flask \
  --report --output-dir ~/Desktop/roary-reports/
```

---

## 5. FastAPI Server

### Start

```bash
# Default: http://127.0.0.1:8000
uv run main.py --server

# Custom host/port (production)
uv run main.py --server --host 0.0.0.0 --port 9000

# With request logging
uv run main.py --server -v
```

### Swagger UI

Open **http://127.0.0.1:8000/docs** in your browser.

You will see two endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/heartbeat` | Liveness probe — used by Paperclip to verify the service is alive |
| `POST` | `/generate-report` | Full four-agent report generation |

Click **POST /generate-report → Try it out** and paste a GitHub URL into
the request body.

### Example `curl` Requests

**Liveness probe:**
```bash
curl http://127.0.0.1:8000/heartbeat
```
```json
{
  "status": "healthy",
  "service": "roary-newsroom",
  "version": "0.4.0",
  "uptime_seconds": 14.2
}
```

**Generate a report:**
```bash
curl -X POST http://127.0.0.1:8000/generate-report \
  -H "Content-Type: application/json" \
  -d '{
    "github_url": "https://github.com/pallets/flask"
  }'
```

**With optional brand context** (Phase 4 Brand Soul integration):
```bash
curl -X POST http://127.0.0.1:8000/generate-report \
  -H "Content-Type: application/json" \
  -d '{
    "github_url": "https://github.com/tiangolo/fastapi",
    "brand_context": "Oceanpark Digital LLC — technical, direct, no buzzwords.",
    "output_dir": "outputs/oceanpark"
  }'
```

**Truncated response shape:**
```json
{
  "repo_name": "pallets/flask",
  "github_url": "https://github.com/pallets/flask",
  "generated_at": "2026-04-02T20:43:30Z",
  "execution_time_seconds": 76.3,
  "token_usage": {
    "total_tokens": 12863,
    "prompt_tokens": 9554,
    "completion_tokens": 3309,
    "cached_prompt_tokens": 0,
    "successful_requests": 4
  },
  "saved_path": "/home/user/roary/outputs/pallets_flask_20260402T204330Z.md",
  "markdown": "# ROARY Report — pallets/flask\n\n..."
}
```

---

## 6. Production Deployment (Ubuntu / Dell Optiplex 3040)

```bash
# 1. Clone and sync — identical environment to macOS dev machine
git clone https://github.com/you/roary.git && cd roary
cp .env.example .env && nano .env    # set OPENROUTER_API_KEY

uv sync                              # resolves from uv.lock — deterministic

# 2. Smoke test
uv run main.py https://github.com/octocat/Hello-World

# 3. Start API server (bind to all interfaces for LAN access)
uv run main.py --server --host 0.0.0.0 --port 8000
```

**Run as a systemd service** (optional):
```ini
# /etc/systemd/system/roary.service
[Unit]
Description=ROARY Newsroom API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/roary
EnvironmentFile=/home/ubuntu/roary/.env
ExecStart=/home/ubuntu/roary/.venv/bin/python main.py --server --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now roary
sudo journalctl -u roary -f
```

---

## 7. Project Layout

```
roary/
├── main.py                  # Unified entry-point: CLI + API server
├── pyproject.toml           # Dependencies managed by uv
├── uv.lock                  # Deterministic lock file — commit this
├── .env                     # Secrets — never commit
├── .env.example             # Template — commit this
├── outputs/                 # Generated Markdown reports
├── data/
│   └── chromadb/            # Persistent vector store (SQLite)
└── src/roary/
    ├── crawler/             # GitHub API + git clone + noise filter
    ├── rag/                 # ChromaDB client + chunking + embeddings
    ├── agents/              # CrewAI actors, tasks, crew assembly
    └── api/                 # FastAPI application
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `EnvironmentError: OPENROUTER_API_KEY is not set` | Missing or empty `.env` | Add your key to `.env` and re-run |
| `400 Provider returned error — Amazon Bedrock` | OpenRouter routing `claude-3.5-sonnet` to Bedrock on your account | Current config uses `claude-sonnet-4.5` which routes via Anthropic direct — no action needed |
| `ModuleNotFoundError` on first run | Dependency not installed | Run `uv sync` |
| Embedding model download hangs | First-run download of `all-MiniLM-L6-v2` (~90 MB) | Wait ~60s; cached to `~/.cache/huggingface` thereafter |
| Report takes > 3 minutes | Normal for large READMEs | OpenRouter rate limits may add latency; the $0.50/report budget still holds |
| `chromadb` collection error | Stale DB from old schema | Delete `./data/chromadb/` and re-run |
