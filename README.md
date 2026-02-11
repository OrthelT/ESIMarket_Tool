# ESI Structure Market Tools for Eve Online
## Version 0.2.0

Tool for retrieving and analyzing data from Eve Online player-owned markets. Written in Python 3.11+.

## Change Log
- **Version 0.2.0** - Architecture refactoring: modular design, CLI support, headless mode, OAuth callback server
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
- `uv` package manager (recommended) or pip

### Quick Install with uv (Recommended)
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
   git clone https://github.com/yourusername/esi-market-tool.git
   cd esi-market-tool # Git automatically installs in a new folder in your current directory. 
   ```

3. Run UV sync:
```bash
    uv sync
```

### Quick Setup (Recommended)
Run the interactive setup wizard:
```bash
uv run python setup.py
```

This will guide you through configuring:
- Your Eve developers account. 
- EVE API credentials (CLIENT_ID, SECRET_KEY) 
- ESI settings (structure ID, region)
- Rate limiting options
- Google Sheets integration (optional)

**Run a Market Query:**
```bash
uv run esi_markets.py
```

## Advanced Configuration
### Alternative: pip installation
1. Install Python 3.11 or later:
   - Windows: Download from [python.org](https://www.python.org/downloads/)
   - macOS: `brew install python@3.11` (using Homebrew)
   - Linux: `sudo apt install python3.11` (Ubuntu/Debian)

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   # activate your virtual environment
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e .

#### Manual Setup
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
├── market_data.py          # Pure data processing (pandas operations)
├── export.py               # CSV writing and Google Sheets updates
├── file_cleanup.py         # File management
├── get_jita_prices.py      # Jita price retrieval
├── logging_utils.py        # Logging configuration
├── data/
│   ├── type_ids.csv        # Items to track (production)
│   └── type_ids_test.csv   # Test items list
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
- **`[mode]`** - Operational modes
  - `prompt_config_mode`: Enable/disable interactive configuration prompts (CLI flags override this)
- **`[esi]`** - ESI API settings
  - `structure_id`: Structure to monitor (default: 4-HWWF Keepstar)
  - `region_id`: Region for market history (default: Vale of the Silent)
- **`[paths]`** - File locations
  - `output_dir`: Where to save output files (default: `output/`)
  - Data file paths for type IDs (production and test)
- **`[logging]`** - Logging configuration
  - `verbose_console_logging`: Control console output detail
- **`[rate_limiting]`** - Request throttling
  - `market_orders_wait_time`: Delay between market requests (default: 0.1s)
  - `market_history_wait_time`: Delay between history requests (default: 0.3s)
- **`[google_sheets]`** - Google Sheets integration
  - `enabled`: Enable/disable automatic Google Sheets updates (default: false)
  - `credentials_file`: Path to Google service account credentials
  - `workbook_id`: Your Google Sheets workbook ID

See `config.toml.example` for full configuration options with detailed comments.

### Configuration Priority
CLI flags override config.toml settings:
1. **`--headless`** forces standard mode, CSV output, no prompts
2. **`--mode test|standard`** skips the interactive mode prompt
3. **`--no-sheets`** disables Google Sheets regardless of config
4. **`--output-dir`** overrides the configured output directory

Note: If Google Sheets update fails, the script will continue running and save data locally. Check the logs for any update errors.

## Usage

### Basic Usage
Run the script interactively:
```bash
uv run python esi_markets.py
```

On first run, the script will:
1. Open your browser for Eve SSO authentication
2. Automatically capture the OAuth callback (no manual URL pasting required)
3. Prompt for test or standard mode (if `prompt_config_mode = true` in config.toml)
4. Fetch market data and save to CSV files

### CLI Flags

The tool supports command-line flags for automation and scripting:

```bash
# Headless mode (no prompts, for cron/scheduled runs)
uv run python esi_markets.py --headless

# Specify mode explicitly (skips interactive prompt)
uv run python esi_markets.py --mode test      # Test mode: 3 pages only
uv run python esi_markets.py --mode standard  # Standard mode: all pages

# Skip Google Sheets update (even if enabled in config)
uv run python esi_markets.py --no-sheets

# Custom output directory
uv run python esi_markets.py --output-dir ~/market-data

# Combine flags for automation
uv run python esi_markets.py --headless --no-sheets --output-dir /data/eve
```

### Running Modes

1. **Test Mode**: Limited data pull for testing configuration
   - Uses `data/type_ids_test.csv` (abbreviated item list)
   - Fetches only 3 pages of market orders
   - Skips Google Sheets update

2. **Standard Mode**: Full data collection
   - Uses `data/type_ids.csv` (complete item list)
   - Fetches all available market order pages
   - Updates Google Sheets if enabled

### Scheduled Execution

For automated data collection, see **`docs/SCHEDULING.md`** for detailed setup instructions:
- **Linux/macOS**: cron or systemd timers
- **Windows**: Task Scheduler

Example cron job (runs every 6 hours):
```cron
0 */6 * * * cd /path/to/esi-market-tool && uv run python esi_markets.py --headless >> logs/cron.log 2>&1
```

### ESI Endpoints Used

- **Market Structures**: Paginated market orders (1000 per page)
- **Market History**: 30-day history per item (rate limited to ~300 requests/minute)
- **Universe Names**: Item name lookup from EVE SDE

## Outputs

### CSV Files
- **`marketstats_latest.csv`**: Current market summary with Jita price comparison
- **`marketorders_[timestamp].csv`**: Complete market order listings
- **`markethistory_[timestamp].csv`**: 30-day market history
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

- **`cli.py`**: CLI argument parsing and main orchestration
- **`config.py`**: Configuration management using frozen dataclasses
- **`esi_client.py`**: ESI HTTP client with retry logic and rate limiting
- **`ESI_OAUTH_FLOW.py`**: OAuth2 flow with automatic callback server
- **`market_data.py`**: Pure data processing (no I/O, network-agnostic)
- **`export.py`**: CSV writing and Google Sheets updates
- **`file_cleanup.py`**: File archival and cleanup logic

See `docs/refactoring_log.md` for detailed architecture decisions and `CLAUDE.md` for development guidance.

## Troubleshooting

**"Authentication failed. In headless mode, a valid token.json must exist."**
- Run the tool interactively once to complete OAuth: `uv run python esi_markets.py`
- The OAuth token auto-refreshes, but initial auth requires browser interaction

**Google Sheets update fails**
- Run the setup wizard to verify configuration: `uv run python setup.py`
- Check that the service account email has editor access to your spreadsheet
- Verify `credentials_file` path in `config.toml` is correct
- CSV files are still saved locally even if Sheets update fails

**Output files not appearing**
- Check the `output_dir` path exists and is writable (default: `output/`)
- Use `--output-dir` to specify a custom location if needed

**Rate limit errors from ESI**
- Increase wait times in `config.toml`: `market_orders_wait_time`, `market_history_wait_time`
- The tool monitors ESI error limits and pauses automatically if needed

For questions: Discord @orthel_toralen
