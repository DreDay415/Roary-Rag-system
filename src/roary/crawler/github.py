"""GitHub repository crawler for the ROARY ingestion pipeline.

Two public entry-points:

* :func:`fetch_repo_summary` — Phase 1 lightweight path.  Uses the GitHub
  REST API to pull repo metadata and the decoded README in a single round-trip.
  No disk I/O, no git binary required.

* :func:`crawl` — Phase 2 full-corpus path.  Shallow-clones the repo, walks
  the tree, and returns every clean text/code file for RAG ingestion.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import git

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Filter constants — edit here to tune what reaches the RAG pipeline
# ---------------------------------------------------------------------------

#: Directory names that are always noise. Matched against every component of
#: a file's path so that nested occurrences (e.g. packages/ui/node_modules)
#: are caught too.
IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "dist",
        "build",
        ".next",
        ".nuxt",
        ".svelte-kit",
        "coverage",
        ".nyc_output",
        "vendor",
        "target",        # Rust / Maven
        ".gradle",
        ".idea",
        ".vscode",
        "eggs",
        "*.egg-info",
    }
)

#: File extensions that are always noise (binaries, media, archives, artefacts).
IGNORED_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Dependency locks — already captured in IGNORED_FILENAMES for named files
        ".lock",
        ".sum",
        # Images / media
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
        ".webp",
        ".mp4",
        ".mp3",
        ".wav",
        ".ogg",
        ".mov",
        ".avi",
        # Documents / office
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        # Archives
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".7z",
        ".rar",
        ".tgz",
        # Compiled / native
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".obj",
        ".o",
        ".a",
        ".lib",
        ".pyc",
        ".pyo",
        ".class",
        ".wasm",
        # Fonts
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        # Databases
        ".sqlite",
        ".sqlite3",
        ".db",
        # Misc binary blobs
        ".parquet",
        ".pkl",
        ".npz",
        ".npy",
        ".h5",
        ".hdf5",
        ".bin",
        ".dat",
    }
)

#: Exact filenames that are always noise regardless of extension.
IGNORED_FILENAMES: frozenset[str] = frozenset(
    {
        "uv.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Cargo.lock",
        "poetry.lock",
        "Gemfile.lock",
        "composer.lock",
        "go.sum",
        ".DS_Store",
        "Thumbs.db",
        ".env",           # may contain secrets — never ingest
        ".env.local",
        ".env.production",
    }
)

#: Files larger than this are almost certainly generated/minified — skip them.
MAX_FILE_BYTES: int = 500_000  # 500 KB


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepoFile:
    """A single text file extracted from the repository."""

    path: str
    """Relative path from the repo root, using forward slashes."""

    content: str
    """Full decoded UTF-8 text content."""


@dataclass
class CrawlResult:
    """Everything the downstream RAG pipeline needs from one crawl."""

    repo_url: str
    repo_name: str
    """Canonical ``owner/repo`` identifier."""

    files: list[RepoFile] = field(default_factory=list)
    skipped_count: int = 0
    """Number of files that were filtered out or unreadable."""

    @property
    def total_chars(self) -> int:
        return sum(len(f.content) for f in self.files)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"CrawlResult(repo={self.repo_name!r}, "
            f"files={len(self.files)}, "
            f"skipped={self.skipped_count}, "
            f"chars={self.total_chars:,})"
        )


@dataclass(frozen=True)
class RepoSummary:
    """Lightweight repo snapshot fetched via the GitHub REST API.

    Produced by :func:`fetch_repo_summary` — Phase 1's entry-point.  All
    fields map 1-to-1 to GitHub API response fields so downstream agents
    can reference them directly.
    """

    full_name: str
    """Canonical ``owner/repo`` identifier, e.g. ``"octocat/Hello-World"``."""

    url: str
    """The original URL passed to :func:`fetch_repo_summary`."""

    description: str | None
    """Repository description set by the owner (may be ``None``)."""

    stars: int
    """Current stargazer count (``stargazers_count``)."""

    forks: int
    """Fork count."""

    primary_language: str | None
    """Dominant programming language detected by GitHub (may be ``None``)."""

    topics: list[str]
    """Repository topics / tags."""

    homepage: str | None
    """Project homepage URL if set (may be ``None``)."""

    default_branch: str
    """Name of the default branch, e.g. ``"main"``."""

    created_at: str
    """ISO 8601 creation timestamp, e.g. ``"2011-01-26T19:01:12Z"``."""

    updated_at: str
    """ISO 8601 timestamp of the most recent push."""

    readme_path: str
    """Actual filename as stored in the repo, e.g. ``"README.md"``."""

    readme_content: str
    """Full decoded text of the README file (Markdown)."""

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"RepoSummary(repo={self.full_name!r}, "
            f"stars={self.stars:,}, "
            f"language={self.primary_language!r}, "
            f"readme_chars={len(self.readme_content):,})"
        )


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract ``(owner, repo)`` from any common GitHub URL form.

    Accepts HTTPS, SSH, and bare ``owner/repo`` strings.

    Raises:
        ValueError: If the URL cannot be parsed as a GitHub repo reference.
    """
    url = url.strip().rstrip("/")

    # Normalise SSH → HTTPS-like for the regex below
    url = url.replace("git@github.com:", "github.com/")

    pattern = r"github\.com[/:]([^/]+)/([^/\s#?]+?)(?:\.git)?$"
    match = re.search(pattern, url, re.IGNORECASE)
    if not match:
        raise ValueError(
            f"Cannot parse a GitHub owner/repo from {url!r}. "
            "Expected a URL like https://github.com/owner/repo"
        )
    return match.group(1), match.group(2)


# ---------------------------------------------------------------------------
# File-system filtering
# ---------------------------------------------------------------------------


def _should_skip(rel_path: Path) -> bool:
    """Return True if *rel_path* should be excluded from ingestion."""
    parts = rel_path.parts

    # Check every directory component (not the filename itself)
    for part in parts[:-1]:
        if part in IGNORED_DIRS:
            return True
        # Catch glob-style patterns like "*.egg-info"
        if part.endswith(".egg-info"):
            return True

    filename = parts[-1]
    if filename in IGNORED_FILENAMES:
        return True

    suffix = rel_path.suffix.lower()
    if suffix in IGNORED_EXTENSIONS:
        return True

    return False


def _iter_text_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Walk *root* and yield ``(relative_path, text_content)`` for each clean file."""
    for abs_path in sorted(root.rglob("*")):  # sorted → deterministic ordering
        if not abs_path.is_file():
            continue

        rel_path = abs_path.relative_to(root)

        if _should_skip(rel_path):
            logger.debug("skipped (filter): %s", rel_path)
            continue

        if abs_path.stat().st_size > MAX_FILE_BYTES:
            logger.debug("skipped (size): %s", rel_path)
            continue

        try:
            content = abs_path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, PermissionError, OSError):
            # Binary, protected, or broken symlink — silently drop
            logger.debug("skipped (unreadable): %s", rel_path)
            continue

        yield rel_path, content


# ---------------------------------------------------------------------------
# GitHub REST API helpers
# ---------------------------------------------------------------------------

_API_BASE = "https://api.github.com"
_USER_AGENT = "roary-crawler/0.1 (https://github.com/roary)"


def _api_get(path: str, *, token: str | None = None) -> Any:
    """Make an authenticated GET request to the GitHub REST API.

    Args:
        path: API path, e.g. ``"/repos/owner/repo"``.
        token: Optional personal access token.  Falls back to the
            ``GITHUB_TOKEN`` environment variable so the caller never has to
            pass it explicitly in production.

    Returns:
        Parsed JSON response as a Python dict or list.

    Raises:
        urllib.error.HTTPError: On 4xx / 5xx responses.
        ValueError: If the response body is not valid JSON.
    """
    resolved_token = token or os.environ.get("GITHUB_TOKEN")
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if resolved_token:
        headers["Authorization"] = f"Bearer {resolved_token}"

    url = f"{_API_BASE}{path}"
    req = urllib.request.Request(url, headers=headers)
    logger.debug("GET %s", url)

    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_repo_summary(url: str, *, token: str | None = None) -> RepoSummary:
    """Fetch repo metadata and README via the GitHub REST API.

    This is the Phase 1 lightweight entry-point — no git binary, no disk
    cloning, just two API calls.  Rate limit: 60 req/hr unauthenticated,
    5 000 req/hr with a ``GITHUB_TOKEN``.

    Args:
        url: Public GitHub repository URL, e.g.
            ``"https://github.com/octocat/Hello-World"``.
        token: GitHub personal access token.  Falls back to the
            ``GITHUB_TOKEN`` environment variable when omitted.

    Returns:
        :class:`RepoSummary` with metadata and the decoded README text.

    Raises:
        ValueError: If *url* cannot be parsed as a GitHub repo.
        urllib.error.HTTPError: On API errors (404 = private/missing repo,
            403 = rate limited, etc.).
    """
    owner, repo_name = parse_github_url(url)
    repo_path = f"/repos/{owner}/{repo_name}"
    logger.info("Fetching metadata for %s/%s via GitHub API …", owner, repo_name)

    # ── 1. Repo metadata ────────────────────────────────────────────────────
    meta: dict = _api_get(repo_path, token=token)

    # ── 2. README (GitHub returns base64-encoded content) ───────────────────
    try:
        readme_data: dict = _api_get(f"{repo_path}/readme", token=token)
        raw_content: str = readme_data.get("content", "")
        # GitHub encodes with line-breaks every 60 chars — strip them first
        readme_text = base64.b64decode(raw_content.replace("\n", "")).decode(
            "utf-8", errors="replace"
        )
        readme_path: str = readme_data.get("name", "README.md")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Repo exists but has no README — not a hard failure
            logger.warning("No README found for %s/%s", owner, repo_name)
            readme_text = ""
            readme_path = ""
        else:
            raise

    logger.info(
        "Fetched %s/%s — %d stars, %s, README %d chars",
        owner,
        repo_name,
        meta.get("stargazers_count", 0),
        meta.get("language") or "unknown language",
        len(readme_text),
    )

    return RepoSummary(
        full_name=meta["full_name"],
        url=url,
        description=meta.get("description"),
        stars=meta.get("stargazers_count", 0),
        forks=meta.get("forks_count", 0),
        primary_language=meta.get("language"),
        topics=meta.get("topics", []),
        homepage=meta.get("homepage") or None,
        default_branch=meta.get("default_branch", "main"),
        created_at=meta.get("created_at", ""),
        updated_at=meta.get("updated_at", ""),
        readme_path=readme_path,
        readme_content=readme_text,
    )


def crawl(url: str, *, clone_depth: int = 1) -> CrawlResult:
    """Clone a public GitHub repository and return its clean text files.

    The repo is cloned into a temporary directory that is always cleaned up,
    even if an exception is raised mid-walk.

    Args:
        url: Public GitHub repository URL (HTTPS or SSH).
        clone_depth: Shallow clone depth. ``1`` fetches only the latest
            commit (fastest). Pass ``0`` for a full history clone.

    Returns:
        :class:`CrawlResult` with filtered :class:`RepoFile` objects.

    Raises:
        ValueError: If *url* cannot be parsed as a GitHub repo.
        git.GitCommandError: If the clone fails (e.g. private repo, bad URL).
    """
    owner, repo_name = parse_github_url(url)
    clone_url = f"https://github.com/{owner}/{repo_name}.git"
    full_name = f"{owner}/{repo_name}"

    logger.info("Cloning %s (depth=%s) …", full_name, clone_depth or "full")

    tmp_dir = tempfile.mkdtemp(prefix="roary_")
    try:
        clone_kwargs: dict = {
            "to_path": tmp_dir,
            "single_branch": True,
        }
        if clone_depth > 0:
            clone_kwargs["depth"] = clone_depth

        git.Repo.clone_from(clone_url, **clone_kwargs)

        root = Path(tmp_dir)
        total_files = sum(1 for p in root.rglob("*") if p.is_file())

        files: list[RepoFile] = [
            RepoFile(path=str(rel_path).replace("\\", "/"), content=content)
            for rel_path, content in _iter_text_files(root)
        ]

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    skipped = total_files - len(files)
    logger.info(
        "Crawl complete: %d files kept, %d skipped (%.0f%% noise reduction)",
        len(files),
        skipped,
        100 * skipped / total_files if total_files else 0,
    )

    return CrawlResult(
        repo_url=url,
        repo_name=full_name,
        files=files,
        skipped_count=skipped,
    )
