"""
All file I/O and external export for ESI Market Tool.

CSV writing and Google Sheets updates.
"""

import csv
import logging
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from config import AppConfig

logger = logging.getLogger(__name__)

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def save_orders_csv(orders: list[dict], output_dir: Path) -> Path:
    """Save raw market orders to a timestamped CSV in output_dir.

    Returns the path to the written file.
    """
    from datetime import datetime
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"marketorders_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"

    fields = ['type_id', 'order_id', 'price', 'volume_remain', 'volume_total', 'is_buy_order', 'issued', 'range']
    with open(filename, mode='w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for order in orders:
            writer.writerow({field: order.get(field) for field in fields})

    logger.info(f"Market orders saved to {filename}")
    return filename


def save_history_csv(history_df: pd.DataFrame, output_dir: Path) -> Path:
    """Save market history to a timestamped CSV in output_dir."""
    from datetime import datetime
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"markethistory_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"

    columns = ['date', 'type_id', 'highest', 'lowest', 'average', 'order_count', 'volume']
    history_df[columns].to_csv(filename, index=False)

    logger.info(f"Market history saved to {filename}")
    return filename


def save_stats_csv(stats_df: pd.DataFrame, output_dir: Path) -> Path:
    """Save market stats to a timestamped CSV in output_dir."""
    from datetime import datetime
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"marketstats_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"

    stats_df.to_csv(filename, index=False)
    logger.info(f"Market stats saved to {filename}")
    return filename


def save_jita_csv(jita_df: pd.DataFrame, latest_dir: Path) -> Path:
    """Save Jita prices to the latest directory."""
    latest_dir.mkdir(parents=True, exist_ok=True)
    filename = latest_dir / "jita_prices.csv"
    jita_df.to_csv(filename, index=False)
    logger.info(f"Jita prices saved to {filename}")
    return filename


# -----------------------------------------------
# Google Sheets
# -----------------------------------------------

def _update_worksheet(
    workbook: gspread.spreadsheet.Spreadsheet,
    worksheet_name: str,
    csv_path: str | Path,
) -> None:
    """Update a single Google Sheets worksheet from a CSV file."""
    df = pd.read_csv(csv_path)
    df = df.dropna()
    df = df.infer_objects().fillna(0).reset_index(drop=True)

    try:
        worksheet = workbook.worksheet(worksheet_name)
        worksheet.update([df.columns.tolist()] + df.values.tolist())
        logger.info(f"Updated {worksheet_name} from {csv_path}")
    except Exception as e:
        logger.error(f"Error updating {worksheet_name}: {e}")
        raise


def update_all_google_sheets(config: AppConfig) -> None:
    """Update all Google Sheets worksheets from latest CSV files."""
    gs = config.google_sheets
    creds = Credentials.from_service_account_file(gs.credentials_file, scopes=GOOGLE_SCOPES)
    client = gspread.authorize(credentials=creds)

    workbook_id = gs.workbook_id
    if workbook_id.startswith('http'):
        workbook_id = gspread.utils.extract_id_from_url(workbook_id)

    try:
        wb = client.open_by_key(workbook_id)
    except Exception as e:
        raise ValueError(f"Error opening workbook: {e}")

    csv_paths = config.paths.csv
    worksheets = gs.worksheets

    _update_worksheet(wb, worksheets.market_stats, csv_paths.market_stats)
    _update_worksheet(wb, worksheets.jita_prices, csv_paths.jita_prices)
    _update_worksheet(wb, worksheets.market_history, csv_paths.market_history)
