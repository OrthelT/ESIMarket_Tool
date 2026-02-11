"""
Configuration loading and validation for ESI Market Tool.

Single source of truth — all modules import config from here.
"""

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class ESIConfig:
    structure_id: int = 1035466617946
    region_id: int = 10000003


@dataclass(frozen=True)
class LoggingConfig:
    verbose_console_logging: bool = True


@dataclass(frozen=True)
class UserAgentConfig:
    app_name: str = "ESI-Market-Tool"
    app_version: str = "0.2.0"
    email: str = ""
    discord: str = ""
    eve_character: str = ""
    source_url: str = ""

    def format_header(self) -> str:
        """Build a User-Agent string from configured fields.

        Format: AppName/Version (contact info; source URL)
        """
        parts = []
        if self.email:
            parts.append(self.email)
        if self.discord:
            parts.append(f"Discord: {self.discord}")
        if self.eve_character:
            parts.append(f"IGN: {self.eve_character}")
        if self.source_url:
            parts.append(self.source_url)

        header = f"{self.app_name}/{self.app_version}"
        if parts:
            header += f" ({'; '.join(parts)})"
        return header


@dataclass(frozen=True)
class RateLimitConfig:
    market_orders_wait_time: float = 0.1
    market_history_wait_time: float = 0.3


@dataclass(frozen=True)
class WorksheetNames:
    market_stats: str = "market_stats"
    jita_prices: str = "jita_prices"
    market_history: str = "market_history"


@dataclass(frozen=True)
class GoogleSheetsConfig:
    enabled: bool = False
    credentials_file: str = "google_credentials.json"
    workbook_id: str = ""
    worksheets: WorksheetNames = WorksheetNames()


@dataclass(frozen=True)
class CsvPaths:
    market_stats: str = "output/latest/marketstats_latest.csv"
    jita_prices: str = "output/latest/jita_prices.csv"
    market_history: str = "output/latest/markethistory_latest.csv"


@dataclass(frozen=True)
class DataPaths:
    type_ids: str = "data/type_ids.csv"


@dataclass(frozen=True)
class PathsConfig:
    csv: CsvPaths = CsvPaths()
    data: DataPaths = DataPaths()
    output_dir: str = "output"


@dataclass(frozen=True)
class AppConfig:
    esi: ESIConfig = ESIConfig()
    user_agent: UserAgentConfig = UserAgentConfig()
    logging: LoggingConfig = LoggingConfig()
    rate_limiting: RateLimitConfig = RateLimitConfig()
    google_sheets: GoogleSheetsConfig = GoogleSheetsConfig()
    paths: PathsConfig = PathsConfig()
    project_root: Path = Path(".")

    def resolve_path(self, path: str | Path) -> Path:
        """Resolve a path relative to project_root.

        - Expands ~ to home directory
        - Returns absolute paths unchanged
        - Resolves relative paths against project_root
        """
        p = Path(path).expanduser()
        if p.is_absolute():
            return p
        return self.project_root / p


def print_setup_hint() -> None:
    """Print a helpful message about running setup."""
    print("\n" + "=" * 60)
    print("  CONFIGURATION REQUIRED")
    print("=" * 60)
    print("\n  Run the setup wizard to configure the tool:\n")
    print("    uv run python setup.py")
    print("\n  Or manually create/edit config.toml and .env files.")
    print("  See README.md for detailed instructions.")
    print("=" * 60 + "\n")


def check_env_file(project_root: Path = Path(".")) -> None:
    """Check if .env file exists and has required values."""
    env_file = project_root / ".env"
    if not env_file.exists():
        print_setup_hint()
        raise ConfigurationError(".env file not found. EVE API credentials required.")

    content = env_file.read_text()
    if "CLIENT_ID" not in content or "your_client_id" in content:
        print_setup_hint()
        raise ConfigurationError("CLIENT_ID not configured in .env file.")
    if "SECRET_KEY" not in content or "your_secret_key" in content:
        print_setup_hint()
        raise ConfigurationError("SECRET_KEY not configured in .env file.")


def load_config(config_path: str | Path = "config.toml") -> AppConfig:
    """Load configuration from TOML file and return an AppConfig instance.

    Applies defaults for any missing sections/keys so older config files
    still work after new settings are added.
    """
    config_file = Path(config_path)
    if not config_file.exists():
        print_setup_hint()
        raise ConfigurationError(f"Configuration file '{config_path}' not found.")

    with open(config_file, "rb") as f:
        raw = tomllib.load(f)

    project_root = config_file.resolve().parent

    # Build nested dataclasses with defaults for missing keys
    esi = ESIConfig(**raw.get("esi", {}))
    user_agent = UserAgentConfig(**raw.get("user_agent", {}))
    logging_cfg = LoggingConfig(**raw.get("logging", {}))
    rate_limiting = RateLimitConfig(**raw.get("rate_limiting", {}))

    gs_raw = raw.get("google_sheets", {})
    worksheets_raw = gs_raw.pop("worksheets", {}) if "worksheets" in gs_raw else {}
    worksheets = WorksheetNames(**worksheets_raw)
    google_sheets = GoogleSheetsConfig(**gs_raw, worksheets=worksheets)

    paths_raw = raw.get("paths", {})
    csv_paths = CsvPaths(**paths_raw.get("csv", {}))
    data_paths = DataPaths(**paths_raw.get("data", {}))
    output_dir = paths_raw.get("output_dir", "output")
    paths = PathsConfig(csv=csv_paths, data=data_paths, output_dir=output_dir)

    return AppConfig(
        esi=esi,
        user_agent=user_agent,
        logging=logging_cfg,
        rate_limiting=rate_limiting,
        google_sheets=google_sheets,
        paths=paths,
        project_root=project_root,
    )
