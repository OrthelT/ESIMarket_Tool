# ESI Structure Market Tools for Eve Online
## Version 0.3.0

Tool for retrieving and analyzing data from Eve Online player-owned markets. Written in Python 3.11+.

## Change Log
- **Version 0.3.0** - Architecture refactoring: modular design, CLI support, headless mode, OAuth callback server
- **Version 2.0** - Google Sheets integration

## What it Does

- Authenticates via Eve Online SSO OAuth2 with automatic callback capture
- Retrieves market orders from player-owned structures via ESI market-structures endpoint
- Fetches 30-day market history for specified items
- Retrieves current Jita prices for comparison
- Processes data into summary statistics with configurable logging
- Exports data as CSV files with automatic file management
- Optionally updates Google Sheets workbooks
- Supports headless mode for scheduled/automated runs (cron, systemd, Task Scheduler)

## Installation

### Prerequisites
- Python 3.11 or later
- [`uv`](https://docs.astral.sh/uv/) package manager

### Install
1. Install `uv` if you don't have it:
   ```bash
   # macOS/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Windows (PowerShell)
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. Clone the repository and install dependencies:
   Navigate to the directory where you want to install the app. Then:
   ```bash
   git clone https://github.com/OrthelT/ESIMarket_Tool.git
   cd ESIMarket_Tool # Git automatically installs in a new folder in your current directory.
   ```

3. Run UV sync:
```bash
    uv sync
```

### Setup
Run the interactive setup wizard:
```bash
uv run esi-setup
```
This will guide you through configuring:
- Your Eve developers account. 
- EVE API credentials (CLIENT_ID, SECRET_KEY) 
- ESI settings (structure ID, region)
- Rate limiting options
- Google Sheets integration (optional)

**Run a Market Query:**
```bash
uv run esi-market
```

## Advanced Configuration

### Manual Setup (Alternative to Setup Wizard)

> **If you already ran `uv run esi-setup` above, you can skip this section.** The setup wizard handles all of the steps below automatically.

1. Register through the Eve developer portal: https://developers.eveonline.com/
   - Create an application with scope: `esi-markets.structure_markets.v1`
   - Set callback URL (example: `http://localhost:8000/callback`)
   - Copy your CLIENT_ID and SECRET_KEY

2. Create a `.env` file with your credentials:
```env
CLIENT_ID = 'your_client_id'
SECRET_KEY = 'your_secret_key'
```

3. (Optional) Customize `config.toml` with your preferences:
   - The tool ships with sensible defaults in `config.toml`
   - Edit structure_id, region_id, or other settings as needed
   - See `config.toml.example` for reference

4. Project Structure:
```
project_folder/
├── .env                    # API credentials (CLIENT_ID, SECRET_KEY)
├── config.toml             # Application settings (opinionated defaults)
├── config.toml.example     # Configuration reference
├── pyproject.toml          # Package metadata and dependencies
├── .gitignore
├── setup.py                # Interactive setup wizard (TUI)
├── esi_markets.py          # Entry point (delegates to cli.py)
├── cli.py                  # CLI argument parsing and orchestration
├── config.py               # Configuration management (dataclasses)
├── esi_client.py           # ESI HTTP client (market orders/history)
├── ESI_OAUTH_FLOW.py       # OAuth2 authentication with callback server
├── rate_limiter.py         # Async token bucket rate limiter
├── cache.py                # ESI request caching (conditional requests)
├── market_data.py          # Pure data processing (pandas operations)
├── export.py               # CSV writing and Google Sheets updates
├── file_cleanup.py         # File management
├── get_jita_prices.py      # Jita price retrieval
├── logging_utils.py        # Logging configuration
├── data/
│   ├── type_ids.csv        # Items to track
├── output/
│   ├── latest/             # Most recent data
│   ├── archive/            # Older files (auto-cleaned after 30 days)
│   └── markethistory/      # Historical data (permanent)
└── docs/
    ├── SCHEDULING.md       # Cron/systemd/Task Scheduler setup
    └── refactoring_log.md  # Architecture changes log
```

## Google Sheets Integration Setup

This tool can automatically update a Google Sheets workbook with the latest market data. Here's how to set it up:

### 1. Create a Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Create Project" or select an existing project
3. Give your project a name (e.g., "EVE Market Tools")
4. Click "Create"

### 2. Enable Google Sheets API
1. In your project, go to "APIs & Services" > "Library"
2. Search for "Google Sheets API"
3. Click on it and press "Enable"
4. Also search for and enable "Google Drive API"

### 3. Create Service Account Credentials
1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "Service Account"
3. Fill in the service account details:
   - Name: "EVE Market Tools"
   - ID: will auto-generate
   - Click "Create and Continue"
4. For Role, select "Basic" > "Editor"
5. Click "Done"

### 4. Create and Download Service Account Key
1. In the Credentials page, find your service account
2. Click the three dots (⋮) > "Manage keys"
3. Click "Add Key" > "Create new key"
4. Choose "JSON" format
5. Click "Create" - this will download your credentials file
6. Move the downloaded JSON file to your project directory
7. Rename it to something like `google_credentials.json`

> **Note for WSL Users**: If you're using Windows Subsystem for Linux (WSL), the credentials file will download to your Windows Downloads folder. You can move it to your WSL project directory using one of these methods:
> - Copy the file from Windows Downloads to your WSL project directory using Windows Explorer (access your WSL files at `\\wsl$\Ubuntu\home\your_username\path\to\project`)
> - Or use the `cp` command in WSL:
>   ```bash
>   cp /mnt/c/Users/YourWindowsUsername/Downloads/google_credentials.json /home/your_username/path/to/project/
>   ```

### 5. Create and Share Google Sheet
1. Go to [Google Sheets](https://sheets.google.com)
2. Create a new spreadsheet
3. Create three sheets with these exact names:
   - `market_stats`
   - `jita_prices`
   - `market_history`
4. Get your spreadsheet ID:
   - Open your spreadsheet
   - The ID is in the URL: `https://docs.google.com/spreadsheets/d/[THIS-IS-YOUR-SPREADSHEET-ID]/edit`
5. Share the spreadsheet:
   - Click "Share" button
   - Add the service account email (found in your credentials JSON file)
   - Give it "Editor" access

### 6. Configure the Tool
1. Open `config.toml` and update the Google Sheets section:
```toml
[google_sheets]
enabled = true  # Set to true to enable Google Sheets updates
credentials_file = "google_credentials.json"
workbook_id = "your-spreadsheet-id-here"  # Your spreadsheet ID from step 4
```

The tool will now automatically update your Google Sheet with the latest market data whenever it runs.

> **Important Security Note**: If you're using Git for version control, make sure to add your Google credentials file to `.gitignore` to prevent accidentally sharing your credentials. Add this line to your `.gitignore` file:
```gitignore
google_credentials.json
```

## Configuration

All settings are configured in `config.toml` (ships with opinionated defaults):

### Main Settings
- **`[esi]`** - ESI API settings
  - `structure_id`: Structure to monitor (default: 4-HWWF Keepstar)
  - `region_id`: Region for market history (default: Vale of the Silent)
- **`[paths]`** - File locations
  - `output_dir`: Where to save output files (default: `output/`)
  - Data file paths for type IDs (production and test)
- **`[logging]`** - Logging configuration
  - `verbose_console_logging`: Control console output detail
- **`[rate_limiting]`** - Token bucket rate limiter
  - `burst_size`: Maximum burst before throttling (default: 10)
  - `tokens_per_second`: Steady-state request rate (default: 5.0)
  - `max_retries`: Per-request retry limit (default: 5)
  - `retry_delay`: Initial retry delay in seconds (default: 3.0)
  - `retry_backoff_factor`: Exponential backoff multiplier (default: 2.0)
- **`[caching]`** - ESI request caching
  - `enabled`: Enable/disable conditional request caching (default: true)
  - `cache_file`: Path to history cache file (default: `data/history_cache.json`)
- **`[google_sheets]`** - Google Sheets integration
  - `enabled`: Enable/disable automatic Google Sheets updates (default: false)
  - `credentials_file`: Path to Google service account credentials
  - `workbook_id`: Your Google Sheets workbook ID

See `config.toml.example` for full configuration options with detailed comments.

### Configuration Priority
CLI flags override config.toml settings:
1. **`--headless`** runs the full pipeline with no prompts and progress bars disabled (required for cron)
2. **`-i` / `--interactive`** explicitly selects interactive mode (this is already the default)
3. **`--no-sheets`** disables Google Sheets regardless of config
4. **`--output-dir`** overrides the configured output directory

Note: If Google Sheets update fails, the script will continue running and save data locally. Check the logs for any update errors.

## Usage

### Basic Usage
Run the tool interactively:
```bash
uv run esi-market
```

On first run, the script will:
1. Open your browser for Eve SSO authentication
2. Automatically capture the OAuth callback (no manual URL pasting required)
3. Fetch all market data and save to CSV files

### CLI Flags

The tool supports command-line flags for automation and scripting:

```bash
# Headless mode (no prompts, for cron/scheduled runs)
uv run esi-market --headless

# Interactive mode (this is the default, flag is optional)
uv run esi-market -i

# Skip Google Sheets update (even if enabled in config)
uv run esi-market --no-sheets

# Custom output directory
uv run esi-market --output-dir ~/market-data

# Combine flags for automation
uv run esi-market --headless --no-sheets --output-dir /data/eve
```

### Running Modes

1. **Default (Interactive)**: Menu-driven mode with options to run the full pipeline, orders only, or history only. If config or credentials are missing, offers to launch the setup wizard.
2. **Interactive** (`-i`): Same as default — the flag is kept for explicitness but is no longer required.
3. **Headless** (`--headless`): Full pipeline with progress bars disabled and no interactive prompts. **Required** for cron/scheduled runs. Exits with an error if config is missing (no setup wizard prompt).

### Scheduled Execution

For automated data collection, see **`docs/SCHEDULING.md`** for detailed setup instructions:
- **Linux/macOS**: cron or systemd timers
- **Windows**: Task Scheduler

> **Important:** The `--headless` flag is required for scheduled/automated runs. Without it the tool defaults to interactive mode and will wait for user input.

Example cron job with logging (runs every 6 hours):
```cron
0 */6 * * * cd /path/to/esi-market-tool && uv run esi-market --headless >> logs/cron.log 2>&1
```

### ESI Endpoints Used

- **Market Structures**: Paginated market orders (1000 per page)
- **Market History**: 30-day history per item (rate limited to ~300 requests/minute)
- **Universe Names**: Item name lookup from EVE SDE

## Outputs

### CSV Files
- **`marketstats_latest.csv`**: Current market summary with Jita price comparison
- **`marketorders_latest.csv`**: Complete market order listings
- **`markethistory_latest.csv`**: 30-day market history
- **`jita_prices.csv`**: Current Jita market prices

### File Management
The tool automatically manages output files:
- Latest files copied to `output/latest/` with consistent names
- Older files archived to `output/archive/` with timestamps
- Archive files older than 30 days automatically removed
- Market history files preserved indefinitely in `output/markethistory/`

### Google Sheets (Optional)
If enabled in `config.toml`, the tool updates three worksheets:
- **`market_stats`**: Market summary statistics
- **`jita_prices`**: Jita price comparison data
- **`market_history`**: Historical trading data

## Architecture

The codebase follows a modular architecture with clear separation of concerns:

- **`cli.py`**: CLI argument parsing, interactive mode, and main orchestration
- **`config.py`**: Configuration management using frozen dataclasses
- **`esi_client.py`**: Async ESI HTTP client with retry logic and rate limiting
- **`ESI_OAUTH_FLOW.py`**: OAuth2 flow with automatic callback server
- **`rate_limiter.py`**: Async token bucket rate limiter (DI into ESIClient)
- **`cache.py`**: ESI request caching with conditional requests (ETag/Last-Modified)
- **`market_data.py`**: Pure data processing (no I/O, network-agnostic)
- **`export.py`**: CSV writing and Google Sheets updates
- **`file_cleanup.py`**: File archival and cleanup logic

See `docs/refactoring_log.md` for detailed architecture decisions and `CLAUDE.md` for development guidance.

## Troubleshooting

**"Authentication failed. In headless mode, a valid token.json must exist."**
- Run the tool interactively once to complete OAuth: `uv run esi-market`
- The OAuth token auto-refreshes, but initial auth requires browser interaction

**Google Sheets update fails**
- Run the setup wizard to verify configuration: `uv run esi-setup`
- Check that the service account email has editor access to your spreadsheet
- Verify `credentials_file` path in `config.toml` is correct
- CSV files are still saved locally even if Sheets update fails

**Output files not appearing**
- Check the `output_dir` path exists and is writable (default: `output/`)
- Use `--output-dir` to specify a custom location if needed

**Rate limit errors from ESI**
- Lower `tokens_per_second` or `burst_size` in `config.toml` under `[rate_limiting]`
- The tool uses a token bucket rate limiter and monitors ESI error limits, pausing automatically if needed

For questions: Discord @orthel_toralen
