import os
import sys
import csv
import logging

import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

from config import load_config, check_env_file, ConfigurationError, AppConfig
from esi_client import ESIClient

# LICENSE
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version. This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details. <https://www.gnu.org/licenses/>.
#
# ESI Structure Market Tools for Eve Online VERSION 0.2
# Contact orthel_toralen on Discord with questions.

# Module-level config set by main() before any functions run
_config: AppConfig | None = None
logger: logging.Logger | None = None


def configuration_mode():
    config_choice = input("run in configuration mode? (y/n):")
    if config_choice == 'y':
        test_mode, csv_save_mode = debug_mode()

        print(f"""CONFIGURATION SETTINGS
              -----------------------------------------------
              prompt_config_mode: {_config.mode.prompt_config_mode}
              structure_id: {_config.esi.structure_id}
              region_id: {_config.esi.region_id}
              verbose_console_logging: {_config.logging.verbose_console_logging}
              market_orders_wait_time: {_config.rate_limiting.market_orders_wait_time}
              market_history_wait_time: {_config.rate_limiting.market_history_wait_time}
              update_google_sheets: {_config.google_sheets.enabled}

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
        test_mode = True
        csv_save_mode = input("save output to CSV? (y/n):")
        if csv_save_mode == 'y':
            csv_save_mode = True
        else:
            csv_save_mode = False
    else:
        test_mode = False
        csv_save_mode = True

    return test_mode, csv_save_mode


def save_to_csv(orders, filename):
    """Save raw market orders to CSV."""
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


# ===============================================
# Functions: Process Market Stats
#-----------------------------------------------

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

def merge_market_stats(merged_orders, history_data, sde_names: dict[int, str]):
    """Merge sell orders with history data and SDE names.

    Args:
        merged_orders: Aggregated sell order data
        history_data: Historical market data DataFrame
        sde_names: Dict mapping type_id -> type_name from ESIClient.fetch_sde_names()
    """
    grouped_historical_df = history_merge(history_data)
    merged_data = pd.merge(merged_orders, grouped_historical_df, on='type_id', how='left')

    # Apply SDE names
    name_df = pd.DataFrame([
        {'type_id': tid, 'type_name': name}
        for tid, name in sde_names.items()
    ])
    final_df = pd.merge(merged_data, name_df, on='type_id', how='left')
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


def main():
    """Main entry point for the ESI Market Tool"""
    global _config, logger

    # Load config and validate environment
    try:
        _config = load_config()
        check_env_file(_config.project_root)
    except ConfigurationError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    from file_cleanup import rename_move_and_archive_csv
    from get_jita_prices import get_jita_prices
    from googlesheets_updater import update_all_google_sheets
    from logging_utils import setup_logging

    print("=" * 80)
    print("ESI Structure Market Tools for Eve Online")
    print("=" * 80)

    # Load credentials
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    load_dotenv(dotenv_path=_config.project_root / '.env')
    client_id = os.getenv('CLIENT_ID')
    secret_key = os.getenv('SECRET_KEY')

    logger = setup_logging(log_name='market_structures', verbose_console_logging=_config.logging.verbose_console_logging)

    SCOPE = ['esi-markets.structure_markets.v1']

    orders_filename = f"output/marketorders_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
    history_filename = f"output/markethistory_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
    market_stats_filename = f"output/marketstats_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
    os.makedirs('output/latest', exist_ok=True)

    # Timer start
    start_time = datetime.now()
    logger.info(start_time)

    test_mode = False
    csv_save_mode = True
    if _config.mode.prompt_config_mode:
        logger.info("Configuration mode selected")
        test_mode, csv_save_mode = configuration_mode()

    # Authenticate and create ESI client
    from ESI_OAUTH_FLOW import get_token
    token = get_token(client_id=client_id, secret_key=secret_key, requested_scope=SCOPE)
    client = ESIClient(config=_config, token=token)

    # Fetch market orders
    def _print_progress(msg):
        print(msg, end="" if msg.startswith("\r") else "\n")

    if test_mode:
        logger.info("test mode selected")
        idslocation = _config.paths.data.type_ids_test
        orders_result = client.fetch_market_orders(
            structure_id=_config.esi.structure_id,
            max_pages=3,
            wait_time=_config.rate_limiting.market_orders_wait_time,
            progress_callback=_print_progress,
        )
    else:
        logger.info("standard mode selected")
        idslocation = _config.paths.data.type_ids
        orders_result = client.fetch_market_orders(
            structure_id=_config.esi.structure_id,
            max_pages=None,
            wait_time=_config.rate_limiting.market_orders_wait_time,
            progress_callback=_print_progress,
        )

    market_orders = orders_result.data
    mkt_time_seconds = orders_result.elapsed_seconds
    if market_orders:
        Avg_market_response_time = (mkt_time_seconds * 1000) / len(market_orders)
    else:
        Avg_market_response_time = 0

    logger.info(
        f'Market orders done: {mkt_time_seconds:.2f}s, avg: {Avg_market_response_time:.2f}ms')

    # Read type IDs
    type_idsCSV = pd.read_csv(idslocation)
    try:
        type_ids = type_idsCSV['type_ids'].tolist()
    except KeyError:
        try:
            type_ids = type_idsCSV['type_id'].tolist()
        except KeyError:
            type_ids = type_idsCSV['typeID'].tolist()

    # Fetch market history
    logger.info("Fetching market history...")
    print("-" * 80)
    print(f"Querying ESI history for {len(type_ids)} items.")
    print("-" * 80)
    history_result = client.fetch_market_history(
        region_id=_config.esi.region_id,
        type_ids=type_ids,
        wait_time=_config.rate_limiting.market_history_wait_time,
        progress_callback=_print_progress,
    )
    historical_df = pd.DataFrame(history_result.data)
    hist_time_seconds = history_result.elapsed_seconds
    logger.info(f"History complete: {hist_time_seconds:.2f}s")

    print("\n")
    print("=" * 80)
    print("Market History Complete")
    print("=" * 80)

    # Process data
    orders = pd.DataFrame(market_orders)
    new_filtered_orders = filterorders(type_ids, orders)
    merged_sell_orders = aggregate_sell_orders(new_filtered_orders)

    # Fetch SDE names
    sde_type_ids = merged_sell_orders['type_id'].unique().tolist()
    sde_names = ESIClient.fetch_sde_names(sde_type_ids)

    final_data = merge_market_stats(merged_sell_orders, historical_df, sde_names)
    with_jita_price = get_jita_prices(final_data)

    # Save files
    if csv_save_mode:
        logger.info("-----------saving files and exiting----------------")

        save_to_csv(market_orders, orders_filename)
        new_columns = ['date', 'type_id', 'highest', 'lowest', 'average', 'order_count', 'volume']
        historical_df = historical_df[new_columns]
        historical_df.to_csv(history_filename, index=False)
        final_data.to_csv(market_stats_filename, index=False)

        src_folder = r"output"
        latest_folder = os.path.join(src_folder, "latest")
        archive_folder = os.path.join(src_folder, "archive")
        rename_move_and_archive_csv(src_folder, latest_folder, archive_folder, True)

        logger.info("saving jita data")
        with_jita_price.to_csv('output/latest/jita_prices.csv', index=False)

        if _config.google_sheets.enabled:
            try:
                logger.info("Attempting to update Google Sheets...")
                update_all_google_sheets(_config)
                logger.info("Google Sheets update completed successfully")
            except Exception as e:
                logger.error(f"Failed to update Google Sheets: {str(e)}")
                print("Google Sheets update failed. Run 'uv run python setup.py' to configure.")
                logger.info("Continuing with local file operations...")

    # Final summary
    finish_time = datetime.now()
    total_time = finish_time - start_time

    print("=" * 80)
    print("ESI Request Completed Successfully.")
    print(f"Data for {len(final_data)} items retrieved.")
    if _config.google_sheets.enabled:
        print("Google Sheets update was enabled for this run.")
    print("-" * 80)
    total_time_seconds = total_time.total_seconds()

    logger.info(
        f"Time to complete:\nMARKET ORDERS: {mkt_time_seconds:.2f}s, avg: {Avg_market_response_time:.2f}ms\n"
        f"MARKET_HISTORY: {hist_time_seconds:.2f}s, avg: {hist_time_seconds/max(len(type_ids),1):.2f}ms")
    logger.info(f"TOTAL TIME TO COMPLETE: {total_time_seconds:.2f}s")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
