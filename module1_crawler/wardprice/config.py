"""Environment configuration with optional project-local .env support."""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT  # backwards-compatible alias: .env, config.yaml and data/ live at the repo root
DATA_DIR = REPO_ROOT / "data"
MODULE1_DIR = DATA_DIR / "module1"  # module 1 private files (job DB, per-period snapshots, admin CSV)
HANDOFF_ENV = "LLM_ANSWERS_FILE"


def handoff_path() -> Path:
    """Shared hand-off file read by module 2: env LLM_ANSWERS_FILE > config.yaml input_file > data/llm_answers.jsonl."""
    value = os.environ.get(HANDOFF_ENV, "").strip()
    if not value:
        try:
            import yaml

            cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
            value = str(cfg.get("input_file") or "").strip()
        except (OSError, ImportError, ValueError):
            value = ""
    path = Path(value) if value else DATA_DIR / "llm_answers.jsonl"
    return path if path.is_absolute() else REPO_ROOT / path


def load_env_file(path: Path | None = None) -> None:
    """Load simple KEY=VALUE lines without replacing already-set process variables."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class ResearchAPISettings:
    """Configuration for sourced Q&A via Tavily and an OpenAI-compatible model."""

    model: str
    model_api_key: str
    model_base_url: str
    search_api_key: str

    @classmethod
    def from_env(cls) -> "ResearchAPISettings":
        load_env_file()
        return cls(
            model=os.getenv("OPENAI_MODEL", "gemma-4-31B-it").strip(),
            model_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            model_base_url=os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/"),
            search_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
        )
