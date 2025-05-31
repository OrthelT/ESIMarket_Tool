import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from MarketStructures8 import setup_logging


logger = setup_logging(log_name='gsheets_updater')

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive", ]

#configure the paths to the csv files and the worksheet names
market_stats_csv_path = 'output/latest/marketstats_latest.csv'
jita_prices_csv_path = 'output/latest/jita_prices.csv'
market_history_csv_path = 'output/latest/markethistory_latest.csv'

#configure the worksheet names, make sure they match the names in the spreadsheet
market_stats_worksheet_name = 'market_stats'
jita_prices_worksheet_name = 'jita_prices'
market_history_worksheet_name = 'market_history'

# the workbook id is the string of random characters the workbook in the url of the spreadsheet:
# for example:
    # https://docs.google.com/spreadsheets/d/1JTmVeiq1Tn6msEx2U736xQwikgnyLtIi7ogiBMGsRFc/edit#gid=0
# # the worksheet id is:1JTmVeiq1Tn6msEx2U736xQwikgnyLtIi7ogiBMGsRFc
# workbook_id = "1JTmVeiq1Tn6msEx2U736xQwikgnyLtIi7ogiBMGsRFc"

#configure the credentials file and the workbook id
credentials_file = "your credentials file here.json"
workbook_id = "your workbook id here"


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
