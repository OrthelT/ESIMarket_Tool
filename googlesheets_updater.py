import sys
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import tomllib
from pathlib import Path
from logging_utils import setup_logging


logger = setup_logging(log_name='googlesheets_updater')


class ConfigurationError(Exception):
    """Raised when configuration is missing or invalid"""
    pass


def print_setup_hint():
    """Print a helpful message about running setup"""
    print("\n" + "=" * 60)
    print("  CONFIGURATION REQUIRED")
    print("=" * 60)
    print("\n  Run the setup wizard to configure the tool:\n")
    print("    uv run python setup.py")
    print("\n  Or manually create/edit config.toml and .env files.")
    print("  See README.md for detailed instructions.")
    print("=" * 60 + "\n")


def load_config(config_path="config.toml"):
    """Load configuration from TOML file"""
    config_file = Path(config_path)
    if not config_file.exists():
        print_setup_hint()
        raise ConfigurationError(
            f"Configuration file '{config_path}' not found."
        )

    with open(config_file, 'rb') as f:
        return tomllib.load(f)


# Load configuration with helpful error messages
try:
    config = load_config()
except ConfigurationError as e:
    print(f"\nError: {e}")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive", ]

# Extract configuration values
market_stats_csv_path = config['paths']['csv']['market_stats']
jita_prices_csv_path = config['paths']['csv']['jita_prices']
market_history_csv_path = config['paths']['csv']['market_history']

market_stats_worksheet_name = config['google_sheets']['worksheets']['market_stats']
jita_prices_worksheet_name = config['google_sheets']['worksheets']['jita_prices']
market_history_worksheet_name = config['google_sheets']['worksheets']['market_history']

credentials_file = config['google_sheets']['credentials_file']
workbook_id = config['google_sheets']['workbook_id']


def get_gsheets_client(credentials_file, scopes=SCOPES):
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    gsheets_client = gspread.authorize(credentials=creds)
    print(gsheets_client)
    return gsheets_client

def get_workbook(gsheets_client, workbook_id):
    wb = gsheets_client.open_by_key(workbook_id)
    return wb

def get_worksheet(workbook, worksheet_name):
    sheet = workbook.worksheet(worksheet_name)
    print(sheet.title)
    return sheet

def get_all_worksheets(workbook):
    worksheets = workbook.worksheets()
    return worksheets

def update_market_stats(workbook):
    df = pd.read_csv(market_stats_csv_path)
    
    #clean up any null values so gsheets doesn't throw an error
    df = df.dropna()
    df = df.infer_objects().fillna(0).reset_index(drop=True)

    #update the worksheet with the new data
    try:
        worksheet = get_worksheet(workbook=workbook, worksheet_name=market_stats_worksheet_name)
        worksheet.update([df.columns.tolist()] + df.values.tolist())
        logger.info(f"Updated {market_stats_worksheet_name} worksheet with new data from {market_stats_csv_path}")
    except Exception as e:
        logger.error(f"Error updating {market_stats_worksheet_name} worksheet: {e}")
        raise e

def update_jita_prices(workbook):
    df = pd.read_csv(jita_prices_csv_path)
    df = df.dropna()
    df = df.infer_objects().fillna(0).reset_index(drop=True)
    try:
        worksheet = get_worksheet(workbook=workbook, worksheet_name=jita_prices_worksheet_name)
        worksheet.update([df.columns.tolist()] + df.values.tolist())
        logger.info(f"Updated {jita_prices_worksheet_name} worksheet with new data from {jita_prices_csv_path}")
    except Exception as e:
        logger.error(f"Error updating {jita_prices_worksheet_name} worksheet: {e}")
        raise e

def update_market_history(workbook):
    df = pd.read_csv(market_history_csv_path)
    df = df.dropna()
    df = df.infer_objects().fillna(0).reset_index(drop=True)
    try:
        worksheet = get_worksheet(workbook=workbook, worksheet_name=market_history_worksheet_name)
        worksheet.update([df.columns.tolist()] + df.values.tolist())
        logger.info(f"Updated {market_history_worksheet_name} worksheet with new data from {market_history_csv_path}")
    except Exception as e:
        logger.error(f"Error updating {market_history_worksheet_name} worksheet: {e}")
        raise e


def update_all_google_sheets():
    gsheets_client = get_gsheets_client(credentials_file=credentials_file, scopes=SCOPES)
    wb = get_workbook(gsheets_client=gsheets_client, workbook_id=workbook_id)
    try:
        update_market_stats(workbook=wb)
    except Exception as e:
        logger.error(f"Error updating {market_stats_worksheet_name} worksheet: {e}")
        print(f"Error updating {market_stats_worksheet_name} worksheet: {e}")
        raise e
    try:
        update_jita_prices(workbook=wb)
    except Exception as e:
        logger.error(f"Error updating {jita_prices_worksheet_name} worksheet: {e}")
        print(f"Error updating {jita_prices_worksheet_name} worksheet: {e}")
        raise e
    try:
        update_market_history(workbook=wb)
    except Exception as e:
        logger.error(f"Error updating {market_history_worksheet_name} worksheet: {e}")
        print(f"Error updating {market_history_worksheet_name} worksheet: {e}")
        raise e

if __name__ == "__main__":
    try:
        update_all_google_sheets()
    except Exception as e:
        logger.error(f"Error updating Google Sheets: {e}")
        print(f"Error updating Google Sheets: {e}")
        
        raise e
