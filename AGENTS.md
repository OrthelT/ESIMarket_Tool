# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Refactoring Status

The codebase was refactored from a monolithic `esi_markets.py` into focused modules on the `refactor-architecture` branch. The async migration (aiohttp), token bucket rate limiter, Rich progress bars, User-Agent configuration, type ID management, and setup.py ESI runner have all been completed. See **`docs/refactoring_log.md`** for detailed history and **`docs/CODE_REVIEW.md`** for the original review.

## Project Overview

ESI Structure Market Tools is a Python application for retrieving and analyzing Eve Online player-owned market data via the ESI (EVE Swagger Interface) API. The tool authenticates via OAuth2, fetches market orders and historical data from structures using async HTTP (aiohttp), compares prices with Jita (main trade hub), and optionally exports results to Google Sheets.

## Development Commands

### Environment Setup
This project uses `uv` for dependency management:

```bash
# Install dependencies
uv sync

# Run interactive setup wizard (recommended for first-time setup)
uv run esi-setup

# Run the main application
uv run esi-market
```

### Setup Wizard
The `setup.py` script provides a TUI for configuration:

```bash
uv run esi-setup
```

Features:
- Interactive menus with color-coded options
- Real-time status display for .env and config.toml
- User-Agent configuration for CCP compliance
- Type ID management (import CSV, search ESI by name, view current)
- ESI connectivity test and full pipeline runner
- Rate limiting and Google Sheets configuration

When configuration is missing or invalid, the tool will offer to launch the setup wizard automatically (in interactive mode) or exit with a clear error (in headless mode).

### Running the Application
The main entry point is `esi_markets.py` (delegates to `cli.py`):

```bash
# Interactive mode (default) — Rich progress bars shown
uv run esi-market

# Headless mode for cron/scheduled runs — progress bars disabled
uv run esi-market --headless

# Full automation: headless, no Google Sheets, custom output dir
uv run esi-market --headless --no-sheets --output-dir ~/market-data
```

On first run, it will:
1. Check for valid configuration (suggests setup if missing)
2. Open browser for Eve SSO authentication (auto-captured via callback server)
3. Fetch all market data from configured structure
4. Save results to CSV files in `output/` directory

## Architecture Overview

### Core Data Flow
1. **Configuration** (`config.py`): Frozen dataclasses loaded from `config.toml`
2. **Authentication** (`ESI_OAUTH_FLOW.py`): Synchronous OAuth2 flow with HTTP callback server
3. **Rate Limiting** (`rate_limiter.py`): Async token bucket controls request rate
4. **Market Orders** (`esi_client.py`): Async paginated fetch from ESI structures endpoint
5. **Market History** (`esi_client.py`): Async 30-day historical data per item type
6. **Jita Prices** (`get_jita_prices.py`): Async Jita prices via Fuzzworks API
7. **Data Processing** (`market_data.py`): Aggregates sell orders, statistics, merges datasets
8. **Export** (`export.py`): CSV files + optional Google Sheets update
9. **Cleanup** (`file_cleanup.py`): Archives old files, maintains latest/ folder

### Key Modules

**cli.py** - Async CLI and main orchestration
- argparse CLI with `--headless`, `-i`/`--interactive`, `--output-dir`, `--no-sheets`
- `async def run()` coordinates entire pipeline, called via `asyncio.run()`
- `async def _interactive_run()` provides menu-driven sub-pipeline selection (orders only, history only, or full)
- Market orders and history fetch run **concurrently** via `asyncio.gather()` — tasks are pre-created before `with progress:` starts the Live display
- Rich progress bars with `disable=args.headless` for silent scheduled execution
- Creates `TokenBucketRateLimiter` from config, injects into `ESIClient`
- Supports scheduled/headless execution via cron (see `docs/SCHEDULING.md`)

**config.py** - Configuration management
- Frozen dataclasses mirroring `config.toml` structure (`AppConfig`, `ESIConfig`, `UserAgentConfig`, `RateLimitConfig`, etc.)
- `UserAgentConfig.format_header()` builds CCP-compliant User-Agent string
- `load_config()` factory with defaults for missing keys
- `resolve_path()` for cross-platform path handling (`~`, relative, absolute)

**esi_client.py** - Async ESI HTTP client
- `ESIClient` is an async context manager (`__aenter__`/`__aexit__`) managing an `aiohttp.ClientSession`
- Accepts `TokenBucketRateLimiter` via dependency injection
- `fetch_market_orders()` — async paginated fetch with Rich progress, dynamic total from `X-Pages` header; accepts optional `task_id` for pre-created progress tasks
- `fetch_market_history()` — async per-item fetch with configurable retries and exponential backoff; accepts optional `task_id` for pre-created progress tasks
- `fetch_sde_names()` — instance method, resolves type IDs to names via ESI `/universe/names/`
- `test_connectivity()` — quick single-page fetch for setup.py connectivity check
- All methods use `content_type=None` on `response.json()` for ESI compatibility
- User-Agent header applied to both authenticated and public requests

**rate_limiter.py** - Async token bucket rate limiter
- `TokenBucketRateLimiter` with configurable `burst_size` and `tokens_per_second`
- `async def acquire()` — awaits until a token is available
- Uses `asyncio.Lock` for concurrency safety and `time.monotonic()` for accurate refill

**ESI_OAUTH_FLOW.py** - Authentication handler
- Synchronous OAuth2 flow with Eve Online SSO (runs before async event loop)
- HTTP callback server auto-captures redirect
- `get_token(client_id, secret_key, scope, headless, user_agent)` — dependency injection
- Falls back to manual URL paste if server fails
- Accepts `user_agent` param for CCP-compliant identification

**market_data.py** - Pure data processing
- No I/O, no globals, no network — just DataFrame transformations
- `filter_orders()`, `aggregate_sell_orders()`, `compute_history_stats()`, `merge_market_stats()`

**export.py** - File I/O and Google Sheets
- CSV writing: `save_orders_csv()`, `save_history_csv()`, `save_stats_csv()`, `save_jita_csv()`
- `update_all_google_sheets(config)` with single `_update_worksheet()` helper

**progress_display.py** - Rich progress display
- `MarketProgress` — composes a `Progress` (task tracker) with an explicit `Live` (display manager) inside a styled `Panel`
- Implements `__rich__()` so Live re-renders the Panel from current state each refresh cycle
- Duck-types as `Progress` (provides `add_task()`, `update()`) so `esi_client.py` can use it transparently
- **Important:** Tasks must be pre-created before `with progress:` starts the Live display — adding tasks mid-display causes ghost panel artifacts. See `docs/progress_display_issue.md` for the full debugging history.

**esi_markets.py** - Thin entry point
- Delegates to `cli.main()` — preserves `pyproject.toml` entry point

**get_jita_prices.py** - Async price comparison
- `async def get_jita_prices()` accepts `aiohttp.ClientSession` and `user_agent` params
- Fetches Jita market prices from Fuzzworks aggregates API
- Region ID 10000002 hardcoded for Jita

**cache.py** - ESI request caching
- `HistoryCache` class for conditional requests (ETag/Last-Modified)
- Reduces ESI load by skipping unchanged history data (HTTP 304)
- Serialized to `data/history_cache.json`
- Loaded/saved around history fetch pipeline in `cli.py`

**file_cleanup.py** - File management
- Uses pathlib throughout
- No blocking `input()` calls (headless-safe)

**setup.py** - Interactive setup TUI (standalone, stays synchronous)
- Rich-based menus for all configuration
- User-Agent configuration (app name, version, email, Discord, IGN, source URL)
- Type ID management: import from CSV, search ESI by name, view current list
- Rate limiting configuration (burst size, tokens/sec, retries, delay, backoff)
- ESI query runner: connectivity test and full pipeline execution
- Reads/writes `config.toml` as raw dict (not via `AppConfig`)
- Bridges to async ESIClient via `asyncio.run()` for connectivity tests

### Configuration

All configuration is in `config.toml` (ships with opinionated defaults):

```toml
[esi]
structure_id = 1035466617946  # 4-HWWF Keepstar (default)
region_id = 10000003  # Vale of the Silent (for history)

[user_agent]
app_name = "ESI-Market-Tool"
app_version = "0.3.0"
email = ""           # CCP recommends identifying your app
discord = ""
eve_character = ""
source_url = ""

[logging]
verbose_console_logging = true

[rate_limiting]
burst_size = 10              # Max burst before throttling
tokens_per_second = 5.0      # Steady-state request rate
max_retries = 5              # Per-request retry limit
retry_delay = 3.0            # Initial retry delay (seconds)
retry_backoff_factor = 2.0   # Exponential backoff multiplier

[caching]
enabled = true               # Enable conditional request caching
cache_file = "data/history_cache.json"

[google_sheets]
enabled = false
credentials_file = "google_credentials.json"
workbook_id = "your-spreadsheet-id-here"

[google_sheets.worksheets]
market_stats = "market_stats"
jita_prices = "jita_prices"
market_history = "market_history"

[paths]
output_dir = "output"

[paths.csv]
market_stats = "output/latest/marketstats_latest.csv"
jita_prices = "output/latest/jita_prices.csv"
market_history = "output/latest/markethistory_latest.csv"

[paths.data]
type_ids = "data/type_ids.csv"
```

Configuration is loaded via `tomllib` (Python 3.11+) at startup.

### Data Files

**Input:**
- `config.toml` - Application configuration (opinionated defaults included)
- `.env` - Eve SSO credentials (`CLIENT_ID`, `SECRET_KEY`)
- `data/type_ids.csv` - List of items to track (managed via setup.py or manual edit)

**Output Structure:**
```
output/
├── latest/                    # Always contains latest run
│   ├── marketstats_latest.csv
│   ├── marketorders_latest.csv
│   ├── markethistory_latest.csv
│   └── jita_prices.csv
├── archive/                   # Older files (30 day retention)
└── markethistory/            # Historical data (permanent)
```

### ESI Rate Limiting

**Note:** As of early 2026, ESI market endpoints do not enforce token bucket rate limiting. CCP has indicated this will be implemented in the coming months, so the token bucket is included proactively to be ready when it lands.

Rate limiting uses a two-layer approach:
1. **Token bucket** (`rate_limiter.py`): Proactive rate control — configurable `burst_size` and `tokens_per_second` via `config.toml`. Smooths request rate without hard sleeps. Not yet enforced by ESI but included for forward compatibility.
2. **ESI error headers**: Reactive safety net — monitors `X-ESI-Error-Limit-Remain` header, pauses or stops if error budget is nearly exhausted.

Retries use exponential backoff: `retry_delay * (retry_backoff_factor ** attempt)`, up to `max_retries` attempts per request.

### Google Sheets Setup

If modifying Google Sheets integration, note:
- All settings configured in `config.toml` under `[google_sheets]` section
- Set `enabled = true` to activate Google Sheets updates
- Service account credentials file path: `credentials_file` in config
- Workbook ID from spreadsheet URL: `workbook_id` in config
- Worksheet names configurable under `[google_sheets.worksheets]`
- Updates fail gracefully - local CSV files still saved

### Logging

Rotating log files in `logs/` directory:
- Max 1MB per file, keeps 5 backups
- Format: `timestamp|logger|level|function|line|message`
- Console output respects `verbose_console_logging` setting

## Common Patterns

### Adding New ESI Endpoints
Follow the pattern in `fetch_market_orders()`:
1. Build URL with required parameters
2. Call `await self._rate_limiter.acquire()` before each request
3. Use `async with self._session.get(url, headers=...) as response:`
4. Check `response.status` (not `status_code` — aiohttp convention)
5. Use `await response.json(content_type=None)` for ESI compatibility
6. Monitor `X-ESI-Error-Limit-Remain` header as safety net
7. Implement retry with exponential backoff on failure
8. Accept optional `progress: Progress | None` and `task_id: int | None` for Rich progress display
9. **Progress gotcha:** If the new endpoint will run alongside other fetch methods in `asyncio.gather()`, the caller must pre-create the progress task and pass `task_id`. Do NOT call `progress.add_task()` inside the fetch method while Live is running — this causes ghost panel artifacts. See `docs/progress_display_issue.md`.

### Modifying Data Processing
Data flows through pandas DataFrames:
1. Raw ESI JSON → DataFrame
2. Filter by type_ids from CSV
3. Aggregate/merge operations
4. Add SDE data (names) via ESI `/universe/names/` endpoint
5. Export to CSV

### Error Handling Philosophy
- Never crash on single item/page failure
- Retry with configurable exponential backoff
- Log all errors but continue processing
- Show final summary of errors/retries
- Track failed items in `FetchResult.failed_items`

### Key Dependencies
- `aiohttp` — async HTTP for all ESI and Fuzzworks communication
- `requests` + `requests_oauthlib` — synchronous OAuth2 flow only
- `rich` — progress bars, setup.py TUI
- `pandas` — data processing and CSV I/O
- `gspread` + `oauth2client` — Google Sheets export
