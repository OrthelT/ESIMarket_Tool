# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
The main entry point is `esi_markets.py`. On first run, it will:
1. Check for valid configuration (suggests setup if missing)
2. Prompt for configuration mode (test vs standard)
3. Open browser for Eve SSO authentication
4. Fetch market data from configured structure
5. Save results to CSV files in `output/` directory

### Testing
Use test mode for quick verification:
- Uses `data/type_ids_test.csv` (limited item list)
- Fetches only 3 pages of market orders
- Skips Google Sheets update

## Architecture Overview

### Core Data Flow
1. **Authentication** (`ESI_OAUTH_FLOW.py`): OAuth2 flow with Eve SSO, manages token refresh
2. **Market Orders** (`esi_markets.py`): Paginated fetch from ESI structures endpoint
3. **Market History** (`esi_markets.py`): 30-day historical data per item type
4. **Jita Prices** (`get_jita_prices.py`): Current Jita prices via Fuzzworks API for comparison
5. **Data Processing**: Aggregates sell orders, calculates statistics, merges datasets
6. **Export**: CSV files + optional Google Sheets update (`googlesheets_updater.py`)
7. **Cleanup** (`file_cleanup.py`): Archives old files, maintains latest/ folder

### Key Modules

**esi_markets.py** - Main orchestrator
- Coordinates entire data pipeline
- Two fetch modes: `fetch_market_orders_test_mode()` and `fetch_market_orders_standard_mode()`
- Error handling with retry logic (max 5 retries)
- ESI rate limit monitoring via response headers (`X-ESI-Error-Limit-Remain`)
- Configurable wait times between requests to avoid rate limits

**ESI_OAUTH_FLOW.py** - Authentication handler
- Manages OAuth2 flow with Eve Online SSO
- Stores/refreshes tokens in `token.json`
- Required scope: `esi-markets.structure_markets.v1`
- Uses localhost callback (`http://localhost:8000/callback`)

**get_jita_prices.py** - Price comparison
- Fetches Jita market prices from Fuzzworks aggregates API
- Merges with structure data for price comparison
- Region ID 10000002 hardcoded for Jita

**googlesheets_updater.py** - Google Sheets integration
- Updates three worksheets: `market_stats`, `jita_prices`, `market_history`
- Requires Google service account credentials JSON file
- Updates from files in `output/latest/`

**file_cleanup.py** - File management
- Renames latest files to consistent names in `output/latest/`
- Archives older files to `output/archive/`
- Removes files older than 30 days from archive
- Preserves market history files indefinitely

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
