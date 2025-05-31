# ESI Structure Market Tools for Eve Online
## Version 0.2

Tool for retrieving and analyzing data from Eve Online player-owned markets. Written in Python 3.12.

## Change Log
- **version 2.0** - Implements new functionality to update a Google Sheets workbook

## What it Does

- Authenticates a character through Eve's SSO
- Retrieves market orders from player-owned structures via ESI market-structures endpoint
- Fetches 30-day market history for specified items
- Retrieves current Jita prices for comparison
- Processes data into summary statistics with configurable logging
- Exports data as CSV files with automatic file management
- Automatically updates a Google sheet if selected in the MarketStructures8.py configuration option

## Installation

### Prerequisites
- Python 3.12 or later
- pip (Python package installer)

### Windows
1. Install Python 3.12 from [python.org](https://www.python.org/downloads/)
   - During installation, check "Add Python to PATH"
   - Check "Install pip"

2. Open Command Prompt (cmd) and create a virtual environment:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### macOS/Linux
1. Install Python 3.12:
   - macOS: `brew install python@3.12` (using Homebrew)
   - Linux: `sudo apt install python3.12` (Ubuntu/Debian)

2. Open Terminal and create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### All Platforms
1. Register through the Eve developer portal: https://developers.eveonline.com/
   - Create an application with scope: `esi-markets.structure_markets.v1`
   - Set callback URL (example: `http://localhost:8000/callback`)
   - Copy your CLIENT_ID and SECRET_KEY

2. Create a `.env` file with your credentials:
```env
CLIENT_ID = 'your_client_id'
SECRET_KEY = 'your_secret_key'
```

3. Project Structure:
```
project_folder/
├── .env                    # Credentials
├── .gitignore
├── ESI_OAUTH_FLOW.py      # Authentication handling
├── file_cleanup.py        # File management
├── get_jita_prices.py     # Jita price retrieval
├── MarketStructures8.py   # Main script
├── data/
│   ├── type_ids.csv       # Items to track
│   └── type_ids_test.csv  # Test items list
└── output/
    ├── archive/           # Older files (auto-cleaned after 30 days)
    ├── latest/           # Most recent data
    └── markethistory/    # Historical data
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
1. Open `gsheets_updater.py`
2. Update these two lines with your information:
```python
credentials_file = "google_credentials.json"  # Your downloaded credentials file
workbook_id = "your-spreadsheet-id-here"     # Your spreadsheet ID
```

The tool will now automatically update your Google Sheet with the latest market data whenever it runs.

> **Important Security Note**: If you're using Git for version control, make sure to add your Google credentials file to `.gitignore` to prevent accidentally sharing your credentials. Add this line to your `.gitignore` file:
```gitignore
google_credentials.json
```

## Configuration

Key settings in MarketStructures8.py:
- `prompt_config_mode`: Enable/disable configuration prompts
- `structure_id`: Structure to monitor (default: 4-HWWF Keepstar)
- `region_id`: Region for market history (default: Vale of the Silent)
- `verbose_console_logging`: Control console output detail
- `market_orders_wait_time`: Delay between market requests (default: 0.1s)
- `market_history_wait_time`: Delay between history requests (default: 0.3s)
- `update_google_sheets`: Enable/disable automatic Google Sheets updates (default: False)

To enable Google Sheets updates:
1. Set `update_google_sheets = True` in MarketStructures8.py
2. Make sure you've completed the Google Sheets setup steps above
3. The script will automatically update your Google Sheet after each successful data collection

Note: If Google Sheets update fails, the script will continue running and save data locally. Check the logs for any update errors.

## Usage

Run the script:
```bash
python MarketStructures8.py
```

The script offers two modes:
1. Test Mode: Limited data pull for testing configuration
2. Standard Mode: Full data collection

The script uses two ESI endpoints:
- Market Structures: Returns paginated market orders (1000 per page)
- Market History: Returns 30-day history per item (rate limited to ~300 requests/minute)

## Outputs

- `marketstats_latest.csv`: Current market summary with Jita price comparison
- `marketorders_*.csv`: Complete market order listings
- `markethistory_*.csv`: 30-day market history
- `jita_prices.csv`: Current Jita market prices

File Management:
- Latest files kept in output/latest/
- Older files moved to archive/
- Files older than 30 days automatically removed
- Market history preserved indefinitely

For questions: Discord @orthel_toralen

