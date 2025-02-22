---------------------------------------------
ESI Structure Market Tools for Eve Online
---------------------------------------------
Tool for retrieving and analyzing data from Eve Online player-owned markets. Written in Python 3.12.

## What it Does

- Authenticates a character through Eve's SSO
- Retrieves market orders from player-owned structures via ESI market-structures endpoint
- Fetches 30-day market history for specified items
- Retrieves current Jita prices for comparison
- Processes data into summary statistics with configurable logging
- Exports data as CSV files with automatic file management

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
CLIENT_ID = 'your_client_id'
SECRET_KEY = 'your_secret_key'

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

## Configuration

Key settings in MarketStructures8.py:
- `prompt_config_mode`: Enable/disable configuration prompts
- `structure_id`: Structure to monitor (default: 4-HWWF Keepstar)
- `region_id`: Region for market history (default: Vale of the Silent)
- `verbose_console_logging`: Control console output detail
- `market_orders_wait_time`: Delay between market requests (default: 0.1s)
- `market_history_wait_time`: Delay between history requests (default: 0.3s)

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

