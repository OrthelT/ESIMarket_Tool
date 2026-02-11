# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Refactoring Status

The codebase was refactored from a monolithic `esi_markets.py` into focused modules on the `refactor-architecture` branch. See **`docs/refactoring_log.md`** for detailed progress, commit history, decisions made, and handoff notes for the next Claude instance. See **`docs/CODE_REVIEW.md`** for the original review that motivated the refactoring.

## Project Overview

ESI Structure Market Tools is a Python application for retrieving and analyzing Eve Online player-owned market data via the ESI (EVE Swagger Interface) API. The tool authenticates via OAuth2, fetches market orders and historical data from structures, compares prices with Jita (main trade hub), and optionally exports results to Google Sheets.

## Development Commands

### Environment Setup
This project uses `uv` for dependency management:

```bash
# Install dependencies
uv sync

# Run interactive setup wizard (recommended for first-time setup)
uv run python setup.py

# Run the main application
uv run python esi_markets.py
```

### Setup Wizard
The `setup.py` script provides a beautiful TUI for configuration:

```bash
uv run python setup.py
```

Features:
- Interactive menus with color-coded options
- Real-time status display for .env and config.toml
- Helpful hints and explanations for each setting
- Automatic file generation and updates

When configuration is missing or invalid, running `esi_markets.py` will display a helpful message suggesting to run the setup wizard.

### Running the Application
The main entry point is `esi_markets.py` (delegates to `cli.py`):

```bash
# Interactive mode (default)
uv run python esi_markets.py

# Headless mode for cron/scheduled runs
uv run python esi_markets.py --headless

# Test mode (3 pages only)
uv run python esi_markets.py --mode test

# Full automation: headless, no Google Sheets, custom output dir
uv run python esi_markets.py --headless --no-sheets --output-dir ~/market-data
```

On first run, it will:
1. Check for valid configuration (suggests setup if missing)
2. Prompt for configuration mode (test vs standard) — or use CLI flags
3. Open browser for Eve SSO authentication (auto-captured via callback server)
4. Fetch market data from configured structure
5. Save results to CSV files in `output/` directory

### Testing
Use test mode for quick verification:
- Uses `data/type_ids_test.csv` (limited item list)
- Fetches only 3 pages of market orders
- Skips Google Sheets update

## Architecture Overview

### Core Data Flow
1. **Configuration** (`config.py`): Frozen dataclasses loaded from `config.toml`
2. **Authentication** (`ESI_OAUTH_FLOW.py`): OAuth2 flow with HTTP callback server
3. **Market Orders** (`esi_client.py`): Paginated fetch from ESI structures endpoint
4. **Market History** (`esi_client.py`): 30-day historical data per item type
5. **Jita Prices** (`get_jita_prices.py`): Current Jita prices via Fuzzworks API
6. **Data Processing** (`market_data.py`): Aggregates sell orders, statistics, merges datasets
7. **Export** (`export.py`): CSV files + optional Google Sheets update
8. **Cleanup** (`file_cleanup.py`): Archives old files, maintains latest/ folder

### Key Modules

**cli.py** - CLI and main orchestration
- argparse CLI with `--headless`, `--mode test|standard`, `--output-dir`, `--no-sheets`
- Coordinates entire data pipeline
- Supports scheduled/headless execution via cron (see `docs/SCHEDULING.md`)

**config.py** - Configuration management
- Frozen dataclasses mirroring `config.toml` structure (`AppConfig`, `ESIConfig`, etc.)
- `load_config()` factory with defaults for missing keys
- `resolve_path()` for cross-platform path handling (`~`, relative, absolute)

**esi_client.py** - ESI HTTP client
- `ESIClient` class with `fetch_market_orders()` and `fetch_market_history()`
- Single fetch method with `max_pages` parameter (3 for test, None for standard)
- `progress_callback` for silent headless operation
- `fetch_sde_names()` static method with error handling

**ESI_OAUTH_FLOW.py** - Authentication handler
- OAuth2 flow with Eve Online SSO
- HTTP callback server auto-captures redirect (no more "connection refused")
- `get_token(client_id, secret_key, scope, headless=False)` — dependency injection
- Falls back to manual URL paste if server fails

**market_data.py** - Pure data processing
- No I/O, no globals, no network — just DataFrame transformations
- `filter_orders()`, `aggregate_sell_orders()`, `compute_history_stats()`, `merge_market_stats()`

**export.py** - File I/O and Google Sheets
- CSV writing: `save_orders_csv()`, `save_history_csv()`, `save_stats_csv()`, `save_jita_csv()`
- `update_all_google_sheets(config)` with single `_update_worksheet()` helper

**esi_markets.py** - Thin entry point
- Delegates to `cli.main()` — preserves `pyproject.toml` entry point

**get_jita_prices.py** - Price comparison
- Fetches Jita market prices from Fuzzworks aggregates API
- Region ID 10000002 hardcoded for Jita

**file_cleanup.py** - File management
- Uses pathlib throughout
- No blocking `input()` calls (headless-safe)

### Configuration

All configuration is in `config.toml` (ships with opinionated defaults):

```toml
[mode]
prompt_config_mode = true  # Enable/disable interactive config

[esi]
structure_id = 1035466617946  # 4-HWWF Keepstar (default)
region_id = 10000003  # Vale of the Silent (for history)

[logging]
verbose_console_logging = true  # Console log verbosity

[rate_limiting]
market_orders_wait_time = 0.1  # Delay between order requests
market_history_wait_time = 0.3  # Delay between history requests

[google_sheets]
enabled = false  # Enable Google Sheets export
credentials_file = "google_credentials.json"
workbook_id = "your-spreadsheet-id-here"
```

Configuration is loaded via `tomllib` (Python 3.11+) at startup. Both `esi_markets.py` and `googlesheets_updater.py` read from this file.

### Data Files

**Input:**
- `config.toml` - Application configuration (opinionated defaults included)
- `.env` - Eve SSO credentials (`CLIENT_ID`, `SECRET_KEY`)
- `data/type_ids.csv` - Full list of items to track (production)
- `data/type_ids_test.csv` - Abbreviated list (testing)

**Output Structure:**
```
output/
├── latest/                    # Always contains latest run
│   ├── marketstats_latest.csv
│   ├── markethistory_latest.csv
│   └── jita_prices.csv
├── archive/                   # Older files (30 day retention)
└── markethistory/            # Historical data (permanent)
```

### ESI Rate Limiting

The code monitors two ESI limits:
1. **Error limit**: Tracks `X-ESI-Error-Limit-Remain` header, pauses if < 10 errors remain
2. **Request rate**: Market history limited to ~300 requests/minute, uses wait times to stay under limit

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
Follow the pattern in `fetch_market_orders_standard_mode()`:
1. Build URL with required parameters
2. Include proper headers with OAuth token
3. Check response status and error headers
4. Implement retry logic (max 5 attempts)
5. Add configurable wait time between requests
6. Log all errors and successful fetches

### Modifying Data Processing
Data flows through pandas DataFrames:
1. Raw ESI JSON → DataFrame
2. Filter by type_ids from CSV
3. Aggregate/merge operations
4. Add SDE data (names) via ESI `/universe/names/` endpoint
5. Export to CSV

### Error Handling Philosophy
- Never crash on single item/page failure
- Retry with exponential backoff (3 second delay)
- Log all errors but continue processing
- Show final summary of errors/retries
- Pause for user confirmation on critical failures
