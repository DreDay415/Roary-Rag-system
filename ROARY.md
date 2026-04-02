Product Requirements Document (PRD): Project "Repo-to-Reach"
Product: Autonomous Multi-Agent GitHub Content Repurposer
Environment: Development (macOS / Antigravity), Production (Ubuntu / Dell Optiplex 3040)
Core Frameworks: CrewAI, LangGraph, PydanticAI, ChromaDB, uv

1. Executive Summary
"Repo-to-Reach" is a self-hosted, agentic orchestration system designed to ingest any public GitHub repository and autonomously generate high-fidelity, brand-aligned content marketing assets (LinkedIn threads, technical blog posts, battlecards). It leverages a dual-RAG architecture (one for technical context, one for brand voice) and a multi-agent critique loop to eliminate "AI-slop" and ensure production-ready output.

This project demonstrates enterprise-grade LLM orchestration, cost-routing optimization via OpenRouter, and resilient deployment on local hardware.

2. Target Persona & Use Cases
Primary User: Developer Advocates, Technical Founders, and Marketing Teams (e.g., Oceanpark Digital LLC).

Core Use Case: A user pastes a link to a trending open-source tool or a competitor's public repository. The system clones, chunks, and analyzes the codebase to explain how it works and why it matters, outputting a polished social media campaign in a specific, pre-defined brand voice.

3. System Architecture & Dual-Machine Pipeline
The system is built for extreme portability and local execution.

A. Development Environment (MacBook Pro)
IDE: Google Antigravity (UI, Architecture Planning, Markdown scaffolding).

Terminal Assistant: Claude Code (Executing Python logic, Pydantic schema generation, uv environment management).

Package Management: uv is strictly used to lock dependencies (pyproject.toml and uv.lock) ensuring 1:1 parity when moving to production.

B. Production Environment (Dell Optiplex 3040 / Ubuntu)
Containerization: Docker Compose manages the local ChromaDB vector store.

Orchestration: Python-based CrewAI / LangGraph runtime.

Trigger: A FastAPI endpoint or local watched folder /inputs waiting for a GitHub URL.

4. Functional Requirements
4.1. The "Smart Crawler" (Ingestion Module)
Requirement: The system must accept any public https://github.com/username/repo URL.

Action: It performs a shallow clone or uses the GitHub API to fetch files.

Filtering: It must aggressively filter noise (ignore .git, node_modules, .lock files, and binaries).

Chunking: Code is processed using Syntax-Aware Chunking (grouping functions within their parent classes) rather than blind character counts.

4.2. Dual-RAG Implementation
RAG 1: "Ephemeral Code Context"

Purpose: Stores the embedded chunks of the currently ingested GitHub repo.

Lifecycle: Wiped or isolated after the report is generated.

RAG 2: "Brand Soul"

Purpose: A persistent ChromaDB collection holding brand guidelines, prohibited words (e.g., "delve", "tapestry"), and past high-performing content examples.

4.3. Multi-Agent Crew Definitions (The "Newsroom")
Cost-optimized via OpenRouter.

Agent 1: The Lead Engineer (Model: DeepSeek V3.2)

Goal: Analyze the codebase. Read package.json/requirements.txt to identify the stack. Find the core logic.

Output: A structured JSON technical brief.

Agent 2: The Product Marketer (Model: Claude 3.5 Sonnet)

Goal: Translate the Lead Engineer's technical brief into "Value Propositions." Why does this tool matter to the market?

Agent 3: The Ghostwriter (Model: Claude 3.5 Sonnet)

Goal: Draft the actual content (e.g., LinkedIn thread). It must query the "Brand Soul" RAG to mimic the correct tone.

Agent 4: The Quality Critic (Model: Claude 3.5 Haiku)

Goal: Review the Ghostwriter's draft. Cross-reference with the "Brand Soul" prohibited word list.

Action: If it fails, LangGraph loops it back to the Ghostwriter with revision notes.

4.4. Output & Governance (PydanticAI)
Requirement: All inter-agent communication and final outputs must be strongly typed using Pydantic schemas.

Deliverable: A cleanly formatted Markdown file (.md) saved to the Optiplex's /outputs directory, ready for human review via Paperclip or a simple Gradio UI.

5. Non-Functional Requirements
Cost Efficiency: The entire pipeline must cost less than $0.50 per repository analyzed, utilizing DeepSeek/Haiku for heavy lifting and Sonnet only for final synthesis.

Reproducibility: The uv sync command must flawlessly replicate the MacBook environment on the Optiplex within 60 seconds.

Resilience: API rate limits or OpenRouter timeouts must be handled gracefully with automatic retries and fallback models (e.g., fallback from Sonnet to Gemini).

6. Phased Rollout (The "Crawl, Walk, Run" Plan)
Phase 1: Local Ingestion & Summary (The Crawl)

Set up uv project on MacBook.

Write a Python script to fetch a public GitHub repo's README.md and summarize it using a single agent.

Port to Optiplex, run uv sync, and verify it executes natively.

Phase 2: RAG & Chunking (The Walk)

Spin up ChromaDB in Docker.

Implement the "Smart Crawler" to pull the whole repo, filter it, chunk the actual code, and embed it.

Test querying the codebase manually: "What does the authentication controller do?"

Phase 3: The Multi-Agent Factory (The Run)

Build the 4-agent Crew.

Establish the "Brand Soul" RAG.

Implement the LangGraph cycle so the Critic can reject bad drafts.

Phase 4: Portfolio Polish (The Flex)

Wrap the execution in a FastApi endpoint.

Add tracing via LangSmith/Langfuse to capture a screenshot of the exact token cost and agent reasoning graph for your portfolio presentation.