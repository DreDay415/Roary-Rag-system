# Product Requirements Document (PRD): [PROJECT_NAME]
**Product:** [Brief description of the autonomous system]
**Environment:** Development (macOS / Antigravity), Production (Ubuntu / Dell Optiplex 3040)
**Core Frameworks:** CrewAI, LangGraph, PydanticAI, ChromaDB, uv

## 1. Executive Summary
[High-level mission and why it matters.]

## 2. Target Persona & Use Cases
- [Who is this for?]
- [Core Use Case 1]
- [Core Use Case 2]

## 3. System Architecture & Dual-Machine Pipeline
The system is built for extreme portability and local execution.

### A. Development Environment (MacBook Pro)
- **IDE:** Google Antigravity (UI, Architecture Planning, Markdown scaffolding).
- **Terminal Assistant:** Claude Code (Executing Python logic, Pydantic schema generation, uv environment management).
- **Package Management:** `uv` is strictly used to lock dependencies (`pyproject.toml` and `uv.lock`) ensuring 1:1 parity when moving to production.

### B. Production Environment (Dell Optiplex 3040 / Ubuntu)
- **Containerization:** Docker Compose manages local infrastructure (e.g., ChromaDB, Redis).
- **Orchestration:** Python-based CrewAI / LangGraph runtime.
- **Portability:** Sub-60s deployment via `uv sync`.

## 4. Functional Requirements
### 4.1. [Module Name]
- [Requirement]
- [Requirement]

## 5. Non-Functional Requirements
- **Cost Efficiency:** Target per-run cost < $0.X.
- **Reproducibility:** `uv sync` must flawlessly replicate the MacBook environment on the Optiplex.
- **Resilience:** Handle API rate limits and OpenRouter timeouts with Gemini as the automatic fallback model.

## 6. Phased Rollout (The "Crawl, Walk, Run" Plan)
### Phase 1: Local Setup & Logic (The Crawl)
- [Set up uv project]
- [Write core script]
- [Verify local execution]

### Phase 2: Infrastructure & Data (The Walk)
- [Spin up ChromaDB / database]
- [Implement RAG or core data flow]

### Phase 3: Multi-Agent Factory (The Run)
- [Build Multi-Agent Crew]
- [Implement feedback loop]

### Phase 4: Portfolio Polish (The Flex)
- [Wrap in FastAPI / UI]
- [Add tracing (LangSmith)]
