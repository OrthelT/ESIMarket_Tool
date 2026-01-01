import os
import requests
import time
import csv
import logging
from logging.handlers import RotatingFileHandler

import pandas as pd
from requests import ReadTimeout
from datetime import datetime

from ESI_OAUTH_FLOW import get_token
from file_cleanup import rename_move_and_archive_csv
from get_jita_prices import get_jita_prices
from googlesheets_updater import update_all_google_sheets
from logging_utils import setup_logging

# LICENSE
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version. This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details. <https://www.gnu.org/licenses/>.
#
#ESI Structure Market Tools for Eve Online VERSION 0.2
# #Developed as a learning project, to access Eve's enfeebled ESI. I'm not a real programmer, ok? Don't laugh at me.
# Contact orthel_toralen on Discord with questions.

print("="*80)
print("ESI Structure Market Tools for Eve Online")
print("="*80)

# load environment, where we store our client id and secret key.
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

#CONFIGURATION
prompt_config_mode = True #change this to false if you do not want to be prompted to use configuration mode
structure_id = 1035466617946 # Currently set to 4-HWWF Keepstar. Enter another structure ID for a player-owned structure that you have access to.
region_id = 10000003 # Currently set to Vale of the Silent. Enter another region ID for a different region.
verbose_console_logging = True #change this to false to disable console logging. The log file will still be created.
update_google_sheets = False # Set to True to enable automatic Google Sheets updates

#add a delay between ESI requests to avoid rate limiting.
market_orders_wait_time = 0.1 #change this to increase the wait time between market orders ESI requests.
market_history_wait_time = 0.3 #change this to increase the wait time between market history ESI requests to avoid rate limiting.

# Initialize logger, optional level argument can be passed to set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
logger = setup_logging(log_name='market_structures', verbose_console_logging=verbose_console_logging)

# set variables for ESI requests
MARKET_STRUCTURE_URL = f'https://esi.evetech.net/latest/markets/structures/{structure_id}/?page='
SCOPE = [
    'esi-markets.structure_markets.v1']  #make sure you have this scope enabled in you ESI Dev Application settings.
# output locations
# You can change these file names to be more accurate when pulling data for other regions.
orders_filename = f"output/marketorders_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
history_filename = f"output/markethistory_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
market_stats_filename = f"output/marketstats_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
latest_folder = os.makedirs('output/latest', exist_ok=True)

logger.info(f"MARKET_STRUCTURE_URL: {MARKET_STRUCTURE_URL}\nSCOPE: {SCOPE}")


def configuration_mode():
    config_choice = input("run in configuration mode? (y/n):")
    if config_choice == 'y':
        test_mode, csv_save_mode = debug_mode()

        print(f"""CONFIGURATION SETTINGS
              -----------------------------------------------
              prompt_config_mode: {prompt_config_mode}
              structure_id: {structure_id}
              region_id: {region_id}
              verbose_console_logging: {verbose_console_logging}
              market_orders_wait_time: {market_orders_wait_time}
              market_history_wait_time: {market_history_wait_time}
              update_google_sheets: {update_google_sheets}
              
              These settings will be used for the next run, and can be changed in the code directly.
              -----------------------------------------------
              """)
              
        input("Press Enter to continue or Ctrl+C to exit...")

        return test_mode, csv_save_mode
    else:
        return False, True

def debug_mode():
    test_choice = input("run in testing mode? This will use abbreviated ESI calls for quick debugging (y/n):")
    if test_choice == 'y':
        test_mode = True  # uses abbreviated ESI calls for debugging
        csv_save_mode = input("save output to CSV? (y/n):")
        if csv_save_mode == 'y':
            csv_save_mode = True
        else:
            csv_save_mode = False
    else:
        test_mode = False
        csv_save_mode = True

    return test_mode, csv_save_mode
#

#===============================================
# Functions: Fetch Market Structure Orders
#-----------------------------------------------
def fetch_market_orders_test_mode(test_mode):
    if test_mode:
        print("test mode enabled")

    logger.info("Starting market order fetch in test mode...")
    #initiates the oath2 flow
    
    logger.info("Authorizing ESI scope...")
    #get the token for the ESI scope using the get_token function in the ESO_OAUTH_FLOW.py file
    token = get_token(SCOPE)
    logger.info("ESI scope authorized. Requesting data...")

    #set the headers for the request, this tells ESI that we are requesting JSON data 
    #and that we are using an access token to authenticate our request
    headers = {
        'Authorization': f'Bearer {token["access_token"]}',
        'Content-Type': 'application/json',
    }

    # here we set the variables that we will use to fetch the market orders. 
    # we start at page 1 and set the max pages to 1, we will increment the page number until we have fetched all the pages
    # we will reset the values of max_pages to the number of pages available in the ESI later
    # we also set the retries to 0, this counts the number of times we will retry the request if we get an error so 
    # we don't hit the error limit and get our IP banned
    # we also set the error count to 0, this is the number of errors we have encountered
    #w e also set the total pages to 0, this is the total number of pages we have fetched
    page = 1
    max_pages = 3
    retries: int = 0
    total_retries: int = 0  # Changed from total_tries to total_retries for consistency
    error_count: int = 0
    total_pages = 0

    all_orders = []
    
    logger.info(f"Test mode enabled. Limiting to {max_pages} pages.\n")

    while page <= max_pages:
        response = requests.get(MARKET_STRUCTURE_URL + str(page), headers=headers)

        #set the max pages to the number of pages available in the ESI
        if 'X-Pages' in response.headers:
            max_pages = int(response.headers['X-Pages'])

        #make sure we don't hit the error limit and get our IP banned
        errorsleft = int(response.headers.get('X-ESI-Error-Limit-Remain', 0))
        errorreset = int(response.headers.get('X-ESI-Error-Limit-Reset', 0))

        if errorsleft == 0:
            break
        elif errorsleft < 10:
            logger.warning(f'WARNING: Errors remaining: {errorsleft}. Error limit reset: {errorreset} seconds.\n')

        #some error handling to gently keep prodding the ESI until we get all the data
        if response.status_code != 200:
            error_code = response.status_code
            error_info = response.json()
            error = error_info['error']
            error_count += 1
            
            logger.error(f"Error fetching data from page {page}. status code: {error_code} ({error}. retries: {retries} Retrying in 3 seconds...\n")
            
            if retries < 5:
                retries += 1
                time.sleep(3)
                continue
            else:
                logger.error(f'Reached the 5th retry and giving up on page {page}\n')
                print(f"""Page {page} failed 5 times. Giving up.
                Errors: {error_count}
                Retries: {total_retries}
                Errors left: {errorsleft}
                Time until error reset: {errorreset}
                """)
                input("Press Enter to continue or Ctrl+C to exit...")
                break

        total_retries += retries
        retries = 0

        try:
            #try to decode the json response
            orders = response.json()

        except ValueError:
            #if there is an error decoding the json response, continue the loop
            logger.error(f"Error decoding JSON response from page {page}.\n")
            continue

        if not orders:
            #if there are no orders remaining, break the loop
            logger.error(f"No orders remaining on page {page}.\n")
            break
        
        #add the orders to the list we will use to save to a csv
        all_orders.extend(orders)

        #update the total pages and page number
        logger.info(f"Orders fetched from page {page}/{max_pages}")

        #update the total pages and page number
        total_pages += 1
        page += 1

        #wait for the next page this is to avoid rate limiting and can be configured in the settings at the top of the script.
        print(f"\rNow fetching page {page} of {max_pages}...", end="")
        time.sleep(market_orders_wait_time)

    print(f"""
          -----------------------------------------------
          Market Orders complete. 
          Fetched {total_pages} pages. 
          Total orders: {len(all_orders)}
          Received {error_count} errors.
          {total_retries} total retries.
          -----------------------------------------------
          """)
    logger.info("-----------------------------------------------")
    logger.info("Market Orders complete.")
    logger.info(f"Fetched {total_pages} pages. Total orders: {len(all_orders)}")
    logger.info(f"Received {error_count} errors. {total_retries} total retries.")
    logger.info("-----------------------------------------------")
    logger.info("Returning all orders....")
    return all_orders

def fetch_market_orders_standard_mode():
    logger.info("Starting market order fetch in standard mode...")
    logger.info("-----------------------------------------")
    logger.info("Authorizing ESI scope...")
    # initiates the oath2 flow
    token = get_token(SCOPE)
    logger.info('ESI Scope Authorized. Requesting data.')
    logger.info('-----------------------------------------')

    headers = {
        'Authorization': f'Bearer {token["access_token"]}',
        'Content-Type': 'application/json',
    }

    page = 1
    max_pages = 1
    retries = 0
    total_retries = 0
    error_count = 0
    total_pages = 0
    all_orders = []

    logger.info("fetching market orders...")

    while page <= max_pages:
        logger.debug(f"Fetching page {page}...")
        
        response = requests.get(MARKET_STRUCTURE_URL + str(page), headers=headers)
        logger.debug(f"page: {page}, response: {response.status_code}")
        if 'X-Pages' in response.headers:
            max_pages = int(response.headers['X-Pages'])
        elif response.status_code == 200:
            max_pages = 1
        
        percent_complete = round((page / max_pages) * 100)
        print(f"\rFetching page {page} of {max_pages} ({percent_complete}% complete)", end="")  # Keep progress indicator for user feedback

        # Error limit handling
        errorsleft = int(response.headers.get('X-ESI-Error-Limit-Remain', 0))
        errorreset = int(response.headers.get('X-ESI-Error-Limit-Reset', 0))
        if errorsleft > 0:
            logger.debug(f"Errors remaining: {errorsleft}. Error limit reset: {errorreset} seconds.\n")
        if errorsleft == 0:
            logger.error("Error limit reached. Stopping requests.\n")
            break
        elif errorsleft < 10:
            logger.warning(f'Low error limit remaining: {errorsleft}. Reset in {errorreset} seconds.\n')

        # Error handling
        if response.status_code != 200:
            error_code = response.status_code
            error_details = response.json()
            error = error_details['error']
            error_count += 1
            
            logger.error(f"Error fetching data from page {page}. Status code: {error_code} ({error}). Retries: {retries}\n")
            
            if retries < 5:
                retries += 1
                logger.info(f"Retrying page {page}. Attempt {retries}/5\n")
                time.sleep(3)
                continue
            else:
                logger.error(f'Reached maximum retries for page {page}. Giving up.\n')
                print(f"""
                Page {page} failed after 5 attempts.
                Errors: {error_count}
                Retries: {total_retries}
                Errors left: {errorsleft}
                Time until error reset: {errorreset}
                """)
                input("Press Enter to continue or Ctrl+C to exit...")
                break

        total_retries += retries
        retries = 0

        try:
            orders = response.json()
        except ValueError:
            logger.error(f"Failed to decode JSON response from page {page}\n")
            failed_pages_count += 1
            continue
    

        if not orders:
            logger.info(f"No orders found on page {page}\n")
            break

        all_orders.extend(orders)

        total_pages += 1
        page += 1
        time.sleep(market_orders_wait_time)

    logger.info(f"Retrieved {len(orders)} orders from page {page}/{max_pages}. Total orders: {len(all_orders)}")

    
    logger.info("-----------------------------------------------")
    logger.info("Market Orders Complete")
    logger.info(f"Pages fetched: {total_pages}")
    logger.info(f"Total orders: {len(all_orders)}")
    logger.info(f"Errors: {error_count}")
    logger.info(f"Total retries: {total_retries}")
    logger.info("-----------------------------------------------")
    
    return all_orders

# Save the CSV files
def save_to_csv(orders, filename):
    fields = ['type_id', 'order_id', 'price', 'volume_remain', 'volume_total', 'is_buy_order', 'issued', 'range']
    os.makedirs('output', exist_ok=True)

    with open(filename, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for order in orders:
            writer.writerow({
                'order_id': order.get('order_id'),
                'type_id': order.get('type_id'),
                'price': order.get('price'),
                'volume_remain': order.get('volume_remain'),
                'volume_total': order.get('volume_total'),
                'is_buy_order': order.get('is_buy_order'),
                'issued': order.get('issued'),
                'range': order.get('range')
            })
    logger.info(f"Market orders saved to {filename}")
    # note some IDEs will flag the variable 'file' as an error.
    # This is because DictWriter expects a str, but got a TextIO instead.
    # TextIO does support string writing, so this is not actually an issue.


# update market history
def fetch_market_history(type_id_list: list[int]) -> list[dict[str, int | str | float]]:
    start_time = datetime.now()
    item_count = len(type_id_list)
    logger.info(f"Fetching market history...for {item_count} items")
    logger.info("-"*80)
    estimated_time_seconds = item_count * .54
    estimated_time_minutes = round(estimated_time_seconds / 60)
    print("-"*80)
    print(f"Querying ESI history for {item_count} items. Estimated time to complete: {estimated_time_minutes} minutes")
    print("-"*80)

    timeout = 10
    
    all_history = []
    page = 1
    max_pages = 1
    error_count = 0
    retries = 0
    total_retries = 0
    successful_returns = 0
    failed_items = []
    items_processed = 0

    market_history_url = f'https://esi.evetech.net/latest/markets/{region_id}/history/?datasource=tranquility&type_id='

    # Iterate over type_ids to fetch market history
    for type_id in range(len(type_id_list)):
        item = type_id_list[type_id]
        items_processed += 1
        percent_complete = round((items_processed / len(type_id_list)) * 100)
        
        print(f"\rFetching history for item {items_processed} of {len(type_id_list)}.  {percent_complete}% complete", end="")
        
        while page <= max_pages:
   
            headers = {'accept': 'application/json'}
                
            try:
                request_start_time = datetime.now()
                response = requests.get(market_history_url + str(item), headers=headers, timeout=timeout)
                code = response.status_code
                logger.debug(f"type_id: {item}, status code: {code}")

                error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')
                
                if 'X-Pages' in response.headers:
                    max_pages = int(response.headers['X-Pages'])
                else:
                    max_pages = 1

                if code != 200:
                    error_count += 1
                    error_details = response.json()  # Only try to decode JSON for error responses
                    error = error_details['error']
                    logger.error(f"\nError fetching type_id {item}: Status {response.status_code} ({error})")
                    logger.error(f"Error limit remaining: {error_limit_remain}")
                    if error_limit_remain < 2:
                        logger.error(f"Error limit nearly reached. Stopping requests for {error_limit_reset} seconds to allow reset.\n")
                        time.sleep(error_limit_reset)
                        continue
                    elif retries < 5:
                        retries += 1
                        logger.info(f"\nRetrying type_id {item}. Attempt {retries}/5\n")
                        time.sleep(3)
                        continue
                    else:
                        logger.error(f"\nFailed to fetch type_id {item} after 5 attempts\n")
                        failed_items.append(item)
                        input("Press Enter to continue or Ctrl+C to exit...")
                            
                # Only try to decode JSON for 200 responses
                data = response.json()
                request_duration = datetime.now() - request_start_time

                # Calculate average request duration and check if rate limit is being approached
                if items_processed > 1:
                    average_request_duration = (average_request_duration * (items_processed - 1) + request_duration) / items_processed
                    
                    logger.debug(f"Request for type_id {item} took {request_duration} seconds")
                    logger.debug(f"Average request duration: {average_request_duration} seconds")
                    requests_per_minute = 60 / average_request_duration.total_seconds()
                    logger.debug(f"Requests per minute: {requests_per_minute}")
                    if requests_per_minute > 290:
                        logger.warning(f"Requests per minute limit nearly reached. Current requests per minute: {requests_per_minute}")
                        logger.warning("Sleeping for 10 seconds to avoid exceeding rate limit")
                        time.sleep(10)
                else:
                    average_request_duration = request_duration

                if data:
                    # Add type_id to each record
                    for entry in data:
                        entry['type_id'] = item
                    all_history.extend(data)
                    logger.debug(f"\nRetrieved {len(data)} history records for item {item}\n")
                else:
                    logger.warning(f"\nNo history data found for type_id {item}\n")

                retries = 0
                successful_returns += 1
                page += 1
                time.sleep(market_history_wait_time) #this is the wait time between requests to avoid rate limiting

            except ReadTimeout:
                logger.error(f"\nRequest timeout for type_id {item}\n")
                if retries < 5:
                    retries += 1
                    logger.info(f"\nRetrying after timeout. Attempt {retries}/5\n")
                    time.sleep(3)
                    continue
                else:
                    logger.error(f"\nFailed to fetch type_id {item} after 5 timeout retries\n")
                    failed_items.append(item)
                    break

        total_retries += retries
        retries = 0
        page = 1
        max_pages = 1
        
    finish_time = datetime.now()
    total_time = finish_time - start_time

    print("\n"*2)
    print("="*80)
    print("Market History Complete")
    print("="*80)
    print("\n"*2)

    # Final summary
    logger.info("-----------------------------------------------")
    logger.info("Market History Complete")
    logger.info(f"Items processed: {successful_returns}/{len(type_id_list)}")
    logger.info(f"Total history records: {len(all_history)}")
    logger.info(f"Errors: {error_count}")
    logger.info(f"Total retries: {total_retries}")
    logger.info(f"Total time: {total_time}")
    if failed_items:
        logger.warning(f"Failed items: {failed_items}")
    logger.info("-----------------------------------------------")

    return all_history

# ===============================================
# Functions: Process Market Stats
#-----------------------------------------------
logger.info("processing data and writing to csv")

def filterorders(ids, list_orders):
    filtered_orders = list_orders[list_orders['type_id'].isin(ids)]
    return filtered_orders

def aggregate_sell_orders(orders_data):
    sell_orders = orders_data[orders_data['is_buy_order'] == False]

    grouped_df = sell_orders.groupby('type_id')['volume_remain'].sum().reset_index()
    grouped_df.columns = ['type_id', 'total_volume_remain']

    min_price_df = sell_orders.groupby('type_id')['price'].min().reset_index()
    min_price_df.columns = ['type_id', 'min_price']

    percentile_5th_df = sell_orders.groupby('type_id')['price'].quantile(0.05).reset_index()
    percentile_5th_df.columns = ['type_id', 'price_5th_percentile']

    merged_df = pd.merge(grouped_df, min_price_df, on='type_id')
    merged_df = pd.merge(merged_df, percentile_5th_df, on='type_id')

    return merged_df

def merge_market_stats(merged_orders, history_data):
    grouped_historical_df = history_merge(history_data)
    merged_data = pd.merge(merged_orders, grouped_historical_df, on='type_id', how='left')

    #get typenames from the SDE
    name_data = insert_SDE_data(merged_data)
    final_df = pd.merge(merged_data, name_data, on='type_id', how='left')
    final_df = final_df[['type_id', 'type_name', 'total_volume_remain', 'price_5th_percentile', 'min_price',
       'avg_of_avg_price', 'avg_daily_volume']]
    logger.info("market orders and history data merged")
    return final_df

def history_merge(history_data):
    logger.info(f"merging history data {len(history_data)} items")
    historical_df = history_data
    historical_df['date'] = pd.to_datetime(historical_df['date'])
    last_30_days_df = historical_df[historical_df['date'] >= pd.to_datetime('today') - pd.DateOffset(days=30)]
    grouped_historical_df = last_30_days_df.groupby('type_id').agg(
        avg_of_avg_price=('average', 'mean'),
        avg_daily_volume=('volume', 'mean'),
    ).reset_index()
    grouped_historical_df['avg_of_avg_price'] = grouped_historical_df['avg_of_avg_price'].round(2)
    grouped_historical_df['avg_daily_volume'] = grouped_historical_df['avg_daily_volume'].round(2)
    logger.info("history data merged")
    return grouped_historical_df

def insert_SDE_data(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("querying SDE data")
    base_url = 'https://esi.evetech.net/latest/universe/names/?datasource=tranquility'
    headers = {
        'Content-Type': 'application/json',
    }

    ids = df['type_id'].unique().tolist()
    ids = str(ids)

    data = requests.post(base_url, headers=headers, data=ids)
    resp = data.json()
    df = pd.DataFrame(resp)

    df = df[['id','name']]
    new_cols = {'id': 'type_id','name': 'type_name'}
    df.rename(columns=new_cols, inplace=True)
    logger.info("SDE data query complete")
    return df

if __name__ == '__main__':

    # hit the stopwatch to see how long it takes
    start_time = datetime.now()
    logger.info(start_time)

    test_mode = False
    csv_save_mode = True
    if prompt_config_mode:
        logger.info("Configuration mode selected")
        # Configure to run in an abbreviated test mode....
        test_mode, csv_save_mode = configuration_mode()

    if test_mode:
        logger.info("test mode selected")
        idslocation = 'data/type_ids_test.csv'
        market_orders = fetch_market_orders_test_mode(test_mode)
    else:
        logger.info("standard mode selected")
        idslocation = 'data/type_ids.csv'
        market_orders = fetch_market_orders_standard_mode()

    Mkt_time_to_complete = datetime.now() - start_time
    # Convert timedelta to seconds or milliseconds before rounding
    mkt_time_seconds = Mkt_time_to_complete.total_seconds()
    Avg_market_response_time = (mkt_time_seconds * 1000) / len(market_orders)  # Convert to ms
    
    logger.info(
        f'done. Time to complete market orders: {round(mkt_time_seconds, 2)}s, avg market response time: {round(Avg_market_response_time, 2)}ms')

    # code for retrieving type ids
    type_idsCSV = pd.read_csv(idslocation)

    #added error handling for column labels
    try:
        type_ids = type_idsCSV['type_ids'].tolist()
    except KeyError:
        try:
            type_ids = type_idsCSV['type_id'].tolist()
        except KeyError:
            type_ids = type_idsCSV['typeID'].tolist()

    # update history data
    logger.info("updating history data")
    history_start = datetime.now()
    historical_df = pd.DataFrame(fetch_market_history(type_ids))
    hist_time_to_complete = datetime.now() - history_start
    logger.info(f"history data complete: {hist_time_to_complete}")

    # process data
    orders = pd.DataFrame(market_orders)
    new_filtered_orders = filterorders(type_ids, orders)
    merged_sell_orders = aggregate_sell_orders(new_filtered_orders)
    merge_market_stats(merged_sell_orders, historical_df)

    final_data = merge_market_stats(merged_sell_orders, historical_df)
    with_jita_price = get_jita_prices(final_data)

    # save files
    if csv_save_mode:
        logger.info("-----------saving files and exiting----------------")

        save_to_csv(market_orders, orders_filename)
        # reorder history columns
        new_columns = ['date', 'type_id', 'highest', 'lowest', 'average', 'order_count', 'volume']
        historical_df = historical_df[new_columns]
        historical_df.to_csv(history_filename, index=False)
        final_data.to_csv(market_stats_filename, index=False)

        #save a copy of market stats to update spreadsheet consistently named
        src_folder = r"output"
        latest_folder = os.path.join(src_folder, "latest")
        archive_folder = os.path.join(src_folder, "archive")
        #cleanup files. "Full cleanup true" moves old files from output to archive.
        rename_move_and_archive_csv(src_folder, latest_folder, archive_folder, True)

        logger.info("saving jita data")
        with_jita_price.to_csv('output/latest/jita_prices.csv', index=False)

        # Update Google Sheets if enabled
        if update_google_sheets:
            try:
                logger.info("Attempting to update Google Sheets...")
                update_all_google_sheets()
                logger.info("Google Sheets update completed successfully")
            except Exception as e:
                logger.error(f"Failed to update Google Sheets: {str(e)}")
                print(f"Please check that the credentials file and the workbook id are correct and properly configured in googlesheets_updater.py")
                logger.info("Continuing with local file operations...")
                # Continue execution as the local files are already saved

    # Completed stats
    finish_time = datetime.now()
    total_time = finish_time - start_time

    print("="*80)
    print("ESI Request Completed Successfully.")
    print(f"Data for {len(final_data)} items retrieved.")
    if update_google_sheets:
        print("Google Sheets update was enabled for this run.")
    print("-"*80)
    hist_time_seconds = hist_time_to_complete.total_seconds()
    total_time_seconds = total_time.total_seconds()
    
    logger.info(
        f"Time to complete:\nMARKET ORDERS: {round(mkt_time_seconds, 2)}s, avg: {round(Avg_market_response_time, 
        2)}ms\nMARKET_HISTORY: {round(hist_time_seconds, 2)}s, avg: {round(hist_time_seconds/len(type_ids), 2)}ms")
    logger.info(f"TOTAL TIME TO COMPLETE: {round(total_time_seconds, 2)}s")
    logger.info("="*80)
