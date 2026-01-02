import sys
import gspread
from google.oauth2.service_account import Credentials
from gspread.client import Client
import pandas as pd
import tomllib
from pathlib import Path
from logging_utils import setup_logging
import os

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


def get_gsheets_client(credentials_file: str, scopes: list[str])->gspread.client.Client:
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    gsheets_client = gspread.authorize(credentials=creds)
    print(gsheets_client)
    return gsheets_client

def get_workbook(gsheets_client: gspread.client.Client, workbook_id_or_url: str)->gspread.spreadsheet.Spreadsheet:
    """Get a Google Sheets workbook from a client
    Args:
        gsheets_client: The client to use to get the workbook
        workbook_id_or_url: The ID or URL of the workbook
    Returns:
        The workbook
    """
    if workbook_id_or_url.startswith('http'):
        workbook_id = gspread.utils.extract_id_from_url(workbook_id_or_url)
    else:
        workbook_id = workbook_id_or_url
    try:
        return gsheets_client.open_by_key(workbook_id)
    except Exception as e:
        raise ValueError(f"Error getting workbook: {e} {workbook_id_or_url} maybe you forgot to include a valid workbook ID or URL?")

def get_worksheet(workbook: gspread.spreadsheet.Spreadsheet, worksheet_name: str)->gspread.worksheet.Worksheet:
    sheet = workbook.worksheet(worksheet_name)
    print(sheet.title)
    return sheet

def get_all_worksheets(workbook: gspread.spreadsheet.Spreadsheet)->list[gspread.worksheet.Worksheet]:
    """Get all worksheets from a workbook
    Args:
        workbook: The workbook to get the worksheets from
    Returns:
        A list of worksheet names
    """
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

def import_data(worksheet_name: str, workbook_id_or_url: str, file_path: str):
    """Import data from a file into a worksheet
    Args:
        worksheet_name: The name of the worksheet to import the data into
        workbook_id_or_url: The ID or URL of the workbook
        file_path: The path to the file to import the data from
    Returns:
        None
    """
    client = get_gsheets_client(credentials_file=credentials_file, scopes=SCOPES)
    workbook = get_workbook(gsheets_client=client, workbook_id_or_url=workbook_id)
    worksheet = get_worksheet(workbook=workbook, worksheet_name=worksheet_name)

    #import the data from the file
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
    elif file_path.endswith('.tsv'):
        df = pd.read_table(file_path, sep='\t')
    elif file_path.endswith('.xlsx'):
        df = pd.read_excel(file_path)
    elif file_path.endswith('.json'):
        df = pd.read_json(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_path}")

    #clean up any null values so gsheets doesn't throw an error
    df = df.dropna()
    df = df.infer_objects().fillna(0).reset_index(drop=True)

    #update the worksheet with the new data
    try:
        worksheet = get_worksheet(workbook=workbook, worksheet_name=worksheet_name)
        worksheet.update([df.columns.tolist()] + df.values.tolist())
        logger.info(f"Updated {worksheet_name} worksheet with new data from {file_path}")
    except Exception as e:
        logger.error(f"Error updating {worksheet_name} worksheet: {e}")
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

def test_import_data():

    test_files = os.listdir("data/test_files")
    test_workbook_id_or_url = "https://docs.google.com/spreadsheets/d/1fltqDk3hJJQz12KcFt038LwgpFjJO5--DUyPKAO4uzU/edit?usp=sharing"

    for file in test_files:
        if file.endswith('.csv'):
            worksheet_name = "csv-test"
        elif file.endswith('.tsv'):
            worksheet_name = "tsv_test"
        elif file.endswith('.xlsx'):
            worksheet_name = "xlsx_test"
        elif file.endswith('.json'):
            worksheet_name = "json_test"
        else:
            raise ValueError(f"Unsupported file type: {file}")
        import_data(
            worksheet_name="test",
            workbook_id_or_url=test_workbook_id_or_url,
            file_path=f"data/test_files/{file}"
        )

if __name__ == "__main__":
    client = get_gsheets_client(credentials_file=credentials_file, scopes=SCOPES)

    spreadsheets = client.list_spreadsheet_files()
    sheet_list  = []
    for spreadsheet in spreadsheets:
        sheet_list.append(spreadsheet['name'])

    from rich.prompt import Prompt
    choice_numbers = [str(i) for i in range(1, len(sheet_list) + 1)]
    choice_names = sheet_list
    choice = Prompt.ask(f"Select a sheet to import data into: {choice_numbers}", choices=choice_names)
    print(choice_names[int(choice) - 1])
    for spreadsheet in spreadsheets:
        if spreadsheet['name'] == choice_names[int(choice) - 1]:
            print(spreadsheet['id'])
            break
