"""ROARY — Phase 1 / 2 / 3 / 4 unified entry-point.

Usage
-----
    # Phase 1: fetch and display structured metadata
    uv run main.py https://github.com/owner/repo
    uv run main.py https://github.com/owner/repo --json

    # Phase 2: README RAG — ingest + vector search
    uv run main.py https://github.com/owner/repo -q "What does this tool do?"
    uv run main.py https://github.com/owner/repo --query "How do I install?" -v

    # Phase 3: full four-agent Newsroom report
    uv run main.py https://github.com/owner/repo --report
    uv run main.py https://github.com/owner/repo --report --output-dir my_reports/

    # Phase 4: start the FastAPI server
    uv run main.py --server
    uv run main.py --server --host 0.0.0.0 --port 9000

    uv run main.py --help
"""

from __future__ import annotations

import argparse
import logging
import sys
import textwrap

from langchain_core.documents import Document

from roary.agents.crew import DEFAULT_OUTPUT_DIR, run_report
from roary.crawler.github import fetch_repo_summary
from roary.crawler.parser import RepoData
from roary.rag.ingester import build_embeddings, ingest_readme, query_readme


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roary",
        description="ROARY — autonomous GitHub content repurposer.",
    )

    # Server mode short-circuits all other flags
    parser.add_argument(
        "--server",
        action="store_true",
        help="Start the FastAPI / Uvicorn server (Phase 4 API mode).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        metavar="HOST",
        help="Bind address for --server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        metavar="PORT",
        help="Port for --server (default: 8000)",
    )

    # CLI mode requires a URL
    parser.add_argument(
        "url",
        nargs="?",
        help="Public GitHub repository URL (required unless --server is set)",
    )
    parser.add_argument(
        "-q", "--query",
        default=None,
        metavar="QUERY",
        help="Embed the README into ChromaDB and search for QUERY (Phase 2).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit raw JSON for the repo struct (Phase 1, ignored with --query).",
    )
    parser.add_argument(
        "--token",
        default=None,
        metavar="TOKEN",
        help="GitHub personal access token (falls back to $GITHUB_TOKEN).",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Run the full four-agent Newsroom crew and save a Markdown report.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Directory to save --report output (default: {DEFAULT_OUTPUT_DIR!r}).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable INFO-level logging to stderr.",
    )
    return parser


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _print_human(repo: RepoData) -> None:
    readme_preview = textwrap.shorten(repo.readme, width=300, placeholder=" …")
    print()
    print("┌─ ROARY — Phase 1 Ingestion Result " + "─" * 26)
    print(f"│  repo_name  : {repo.repo_name}")
    print(f"│  description: {repo.description or '(none)'}")
    print(f"│  readme_len : {len(repo.readme):,} chars")
    print("│")
    print("│  README preview:")
    for line in textwrap.wrap(
        readme_preview, width=70,
        initial_indent="│    ", subsequent_indent="│    ",
    ):
        print(line)
    print("└" + "─" * 62)
    print()


def _print_query_results(
    question: str,
    repo_name: str,
    hits: list[Document],
) -> None:
    print()
    print("┌─ ROARY — README Vector Search " + "─" * 30)
    print(f"│  repo  : {repo_name}")
    print(f"│  query : {question!r}")
    print(f"│  hits  : {len(hits)}")
    print("│")
    for i, doc in enumerate(hits, 1):
        chunk_idx = doc.metadata.get("chunk_index", "?")
        print(f"│  ── Hit {i}  [chunk {chunk_idx}] " + "─" * 40)
        for line in textwrap.wrap(
            doc.page_content, width=68,
            initial_indent="│    ", subsequent_indent="│    ",
        ):
            print(line)
        print("│")
    print("└" + "─" * 62)
    print()


def _print_report_summary(result: object) -> None:
    t = result.token_usage
    print()
    print("┌─ ROARY — Report Generated " + "─" * 34)
    print(f"│  repo            : {result.repo_name}")
    print(f"│  saved           : {result.saved_path}")
    print(f"│  execution time  : {result.execution_time_seconds}s")
    print(f"│  tokens total    : {t.total_tokens:,}")
    print(f"│  tokens prompt   : {t.prompt_tokens:,}")
    print(f"│  tokens completion: {t.completion_tokens:,}")
    print(f"│  tokens cached   : {t.cached_prompt_tokens:,}")
    print(f"│  LLM requests    : {t.successful_requests}")
    print("└" + "─" * 62)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    args = _build_parser().parse_args()

    if args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)-8s %(name)s: %(message)s",
            stream=sys.stderr,
        )

    # ── Phase 4: API server mode ─────────────────────────────────────────────
    if args.server:
        try:
            import uvicorn
            from roary.api.main import app
        except ImportError as exc:
            print(f"error: {exc}\nRun: uv add fastapi uvicorn", file=sys.stderr)
            sys.exit(1)

        print(f"Starting ROARY Newsroom API on http://{args.host}:{args.port}")
        print(f"  Docs  → http://{args.host}:{args.port}/docs")
        print(f"  Redoc → http://{args.host}:{args.port}/redoc")
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info" if args.verbose else "warning",
        )
        return

    # All non-server modes require a URL
    if not args.url:
        print("error: a URL is required unless --server is passed.", file=sys.stderr)
        _build_parser().print_usage(sys.stderr)
        sys.exit(1)

    # ── Fetch repo metadata (always required for CLI modes) ──────────────────
    try:
        summary = fetch_repo_summary(args.url, token=args.token)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    repo = RepoData(
        repo_name=summary.full_name,
        description=summary.description,
        readme=summary.readme_content,
    )

    # ── Phase 3: multi-agent report ──────────────────────────────────────────
    if args.report:
        try:
            result = run_report(
                repo,
                output_dir=args.output_dir,
                verbose=args.verbose,
            )
        except EnvironmentError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"error during crew run: {exc}", file=sys.stderr)
            sys.exit(1)

        _print_report_summary(result)
        return

    # ── Phase 2: ingest + query ──────────────────────────────────────────────
    if args.query:
        try:
            embeddings = build_embeddings()
            ingest_readme(repo, embeddings=embeddings)
            hits = query_readme(args.query, repo.repo_name, embeddings=embeddings)
        except Exception as exc:
            print(f"error during RAG pipeline: {exc}", file=sys.stderr)
            sys.exit(1)

        _print_query_results(args.query, repo.repo_name, hits)
        return

    # ── Phase 1: display struct ──────────────────────────────────────────────
    if args.as_json:
        print(repo.model_dump_json(indent=2))
    else:
        _print_human(repo)


if __name__ == "__main__":
    main()
