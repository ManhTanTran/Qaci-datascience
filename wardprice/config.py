"""Environment configuration with optional project-local .env support."""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"true", "1", "yes", "on"}


def bounded_int(name: str, default: int, low: int, high: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < low or value > high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


@dataclass(frozen=True)
class Settings:
    model: str
    api_key: str
    require_search: bool
    max_wards_per_run: int
    max_total_wards: int
    max_calls_per_month: int
    refresh_days: int
    retry_days: int
    max_attempts_per_ward: int
    email_enabled: bool
    gmail_address: str
    gmail_app_password: str
    report_to: str
    max_total_listings: int = 500
    max_new_listings_per_ward: int = 10
    demo_mode: bool = False

    @property
    def database_path(self) -> Path:
        """Return the mode-specific database, refusing cross-mode overrides."""
        production_db = PROJECT_ROOT / "state" / "ward_prices.sqlite3"
        demo_db = PROJECT_ROOT / "state" / "ward_prices.demo.sqlite3"
        configured = os.getenv("WARDPRICE_DB_PATH")
        if self.demo_mode:
            if configured and Path(configured).resolve() != demo_db.resolve():
                raise ValueError(
                    "WARDPRICE_DEMO_MODE requires state/ward_prices.demo.sqlite3; "
                    "remove the production WARDPRICE_DB_PATH override."
                )
            return demo_db
        if configured:
            path = Path(configured)
            if path.resolve() == demo_db.resolve():
                raise ValueError("The demo database requires WARDPRICE_DEMO_MODE=1.")
            return path
        return production_db

    @property
    def output_path(self) -> Path:
        configured = os.getenv("WARDPRICE_OUTPUT_DIR")
        if self.demo_mode:
            return PROJECT_ROOT / "outputs" / "demo"
        return Path(configured) if configured else PROJECT_ROOT / "outputs"

    @classmethod
    def from_env(cls) -> "Settings":
        load_env_file()
        return cls(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            api_key=os.getenv("GEMINI_API_KEY", ""),
            require_search=flag("REQUIRE_SEARCH", False),
            max_wards_per_run=bounded_int("MAX_WARDS_PER_RUN", 2, 1, 50),
            max_total_wards=bounded_int("MAX_TOTAL_WARDS", 100, 1, 100),
            max_calls_per_month=bounded_int("MAX_CALLS_PER_MONTH", 2, 1, 100000),
            refresh_days=bounded_int("REFRESH_DAYS", 30, 1, 365),
            retry_days=bounded_int("RETRY_DAYS", 7, 1, 365),
            max_attempts_per_ward=bounded_int("MAX_ATTEMPTS_PER_WARD", 3, 1, 100),
            email_enabled=flag("ENABLE_EMAIL", False),
            gmail_address=os.getenv("GMAIL_ADDRESS", ""),
            gmail_app_password=os.getenv("GMAIL_APP_PASSWORD", ""),
            report_to=os.getenv("REPORT_TO", ""),
            max_total_listings=bounded_int("MAX_TOTAL_LISTINGS", 500, 1, 500),
            max_new_listings_per_ward=bounded_int("MAX_NEW_LISTINGS_PER_WARD", 10, 1, 50),
            demo_mode=flag("WARDPRICE_DEMO_MODE", flag("DEMO_MODE", False)),
        )


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
