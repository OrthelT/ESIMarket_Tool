import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from logging_utils import setup_logging
from config import AppConfig

logger = setup_logging(log_name='googlesheets_updater')

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gsheets_client(credentials_file: str, scopes: list[str]) -> gspread.client.Client:
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    gsheets_client = gspread.authorize(credentials=creds)
    return gsheets_client


def get_workbook(gsheets_client: gspread.client.Client, workbook_id: str) -> gspread.spreadsheet.Spreadsheet:
    """Get a Google Sheets workbook by ID or URL."""
    if workbook_id.startswith('http'):
        workbook_id = gspread.utils.extract_id_from_url(workbook_id)
    try:
        return gsheets_client.open_by_key(workbook_id)
    except Exception as e:
        raise ValueError(f"Error getting workbook: {e} {workbook_id}")


def get_worksheet(workbook: gspread.spreadsheet.Spreadsheet, worksheet_name: str) -> gspread.worksheet.Worksheet:
    return workbook.worksheet(worksheet_name)


def _update_worksheet(workbook: gspread.spreadsheet.Spreadsheet, worksheet_name: str, csv_path: str) -> None:
    """Update a single worksheet from a CSV file."""
    df = pd.read_csv(csv_path)
    df = df.dropna()
    df = df.infer_objects().fillna(0).reset_index(drop=True)
    try:
        worksheet = get_worksheet(workbook=workbook, worksheet_name=worksheet_name)
        worksheet.update([df.columns.tolist()] + df.values.tolist())
        logger.info(f"Updated {worksheet_name} worksheet with new data from {csv_path}")
    except Exception as e:
        logger.error(f"Error updating {worksheet_name} worksheet: {e}")
        raise


def update_all_google_sheets(config: AppConfig) -> None:
    """Update all Google Sheets worksheets using config for paths and credentials."""
    gs = config.google_sheets
    gsheets_client = get_gsheets_client(credentials_file=gs.credentials_file, scopes=SCOPES)
    wb = get_workbook(gsheets_client=gsheets_client, workbook_id=gs.workbook_id)

    csv = config.paths.csv
    worksheets = gs.worksheets

    _update_worksheet(wb, worksheets.market_stats, csv.market_stats)
    _update_worksheet(wb, worksheets.jita_prices, csv.jita_prices)
    _update_worksheet(wb, worksheets.market_history, csv.market_history)


if __name__ == "__main__":
    pass
