"""
CLI entry point and main orchestration for ESI Market Tool.

Supports interactive mode (default) and --headless for scheduled execution.
"""

import argparse
import asyncio
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from config import load_config, check_env_file, ConfigurationError
from esi_client import ESIClient
from rate_limiter import TokenBucketRateLimiter
from market_data import filter_orders, aggregate_sell_orders, merge_market_stats
from export import (
    save_orders_csv, save_history_csv, save_stats_csv, save_jita_csv,
    update_all_google_sheets,
)
from get_jita_prices import get_jita_prices
from file_cleanup import rename_move_and_archive_csv
from logging_utils import setup_logging

logger: logging.Logger | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog='mktstatus',
        description='ESI Structure Market Tools for Eve Online',
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run without prompts (standard mode, CSV output, no interactive input)',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=None,
        help='Override output directory (default: output/)',
    )
    parser.add_argument(
        '--no-sheets',
        action='store_true',
        help='Skip Google Sheets update even if enabled in config',
    )
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> None:
    """Main orchestration: load config, authenticate, fetch, process, export."""
    global logger

    # 1. Load config
    try:
        config = load_config()
        check_env_file(config.project_root)
    except ConfigurationError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    # 2. Setup logging
    logger = setup_logging(
        log_name='market_structures',
        verbose_console_logging=config.logging.verbose_console_logging,
    )

    # Log User-Agent info
    ua_string = config.user_agent.format_header()
    logger.info(f"User-Agent: {ua_string}")
    if not config.user_agent.email:
        logger.warning("No contact email in [user_agent] config. CCP recommends identifying your app.")

    print("=" * 80)
    print("ESI Structure Market Tools for Eve Online")
    print("=" * 80)

    # 3. Load credentials
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    load_dotenv(dotenv_path=config.project_root / '.env')
    client_id = os.getenv('CLIENT_ID')
    secret_key = os.getenv('SECRET_KEY')

    # 4. Output directory (CLI flag > config > default)
    if args.output_dir:
        output_dir = config.resolve_path(args.output_dir)
    else:
        output_dir = config.resolve_path(config.paths.output_dir)
    latest_dir = output_dir / 'latest'
    latest_dir.mkdir(parents=True, exist_ok=True)

    # 6. Authenticate (sync — runs before async event loop is busy)
    SCOPE = ['esi-markets.structure_markets.v1']
    from ESI_OAUTH_FLOW import get_token
    token = get_token(
        client_id=client_id,
        secret_key=secret_key,
        requested_scope=SCOPE,
        headless=args.headless,
        user_agent=ua_string,
    )
    if token is None:
        print("\nError: Authentication failed. In headless mode, a valid token.json must exist.")
        print("Run interactively first: uv run python esi_markets.py")
        sys.exit(1)

    rate_limiter = TokenBucketRateLimiter(
        burst_size=config.rate_limiting.burst_size,
        tokens_per_second=config.rate_limiting.tokens_per_second,
    )

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        disable=args.headless,
    )

    async with ESIClient(config=config, token=token, rate_limiter=rate_limiter) as esi:
        start_time = datetime.now()
        logger.info(f"Run started at {start_time}")

        # 5. Fetch market orders
        with progress:
            orders_result = await esi.fetch_market_orders(
                structure_id=config.esi.structure_id,
                progress=progress,
            )

        market_orders = orders_result.data
        mkt_time = orders_result.elapsed_seconds
        avg_time = (mkt_time * 1000 / len(market_orders)) if market_orders else 0
        logger.info(f"Market orders: {mkt_time:.2f}s, avg: {avg_time:.2f}ms")

        # 6. Read type IDs
        type_ids_path = config.paths.data.type_ids
        type_ids_df = pd.read_csv(type_ids_path)
        for col in ('type_ids', 'type_id', 'typeID'):
            if col in type_ids_df.columns:
                type_ids = type_ids_df[col].tolist()
                break
        else:
            logger.error(f"No recognized type_id column in {type_ids_path}")
            sys.exit(1)

        # 7. Fetch market history
        with progress:
            history_result = await esi.fetch_market_history(
                region_id=config.esi.region_id,
                type_ids=type_ids,
                progress=progress,
            )
        historical_df = pd.DataFrame(history_result.data)
        hist_time = history_result.elapsed_seconds

        # 8. Process data
        orders_df = pd.DataFrame(market_orders)
        filtered = filter_orders(type_ids, orders_df)
        sell_agg = aggregate_sell_orders(filtered)
        sde_names = await esi.fetch_sde_names(sell_agg['type_id'].unique().tolist())
        final_data = merge_market_stats(sell_agg, historical_df, sde_names)
        with_jita = await get_jita_prices(final_data, session=esi._session, user_agent=ua_string)

    # 11. Save files
    logger.info("Saving CSV files...")
    save_orders_csv(market_orders, output_dir)
    save_history_csv(historical_df, output_dir)
    save_stats_csv(final_data, output_dir)

    # File cleanup: copy latest, archive old files
    src_folder = str(output_dir)
    latest_folder = str(latest_dir)
    archive_folder = str(output_dir / 'archive')
    rename_move_and_archive_csv(src_folder, latest_folder, archive_folder, "archive")

    save_jita_csv(with_jita, latest_dir)

    # 12. Google Sheets
    update_sheets = config.google_sheets.enabled and not args.no_sheets
    if update_sheets:
        try:
            logger.info("Updating Google Sheets...")
            update_all_google_sheets(config)
            logger.info("Google Sheets update completed successfully")
        except Exception as e:
            logger.error(f"Failed to update Google Sheets: {e}")
            print("Google Sheets update failed. Run 'uv run python setup.py' to configure.")

    # 13. Summary
    total_time = (datetime.now() - start_time).total_seconds()

    print("=" * 80)
    print("ESI Request Completed Successfully.")
    print(f"Data for {len(final_data)} items retrieved.")
    if config.google_sheets.enabled and not args.no_sheets:
        print("Google Sheets update was enabled for this run.")
    print("-" * 80)

    logger.info(f"MARKET ORDERS: {mkt_time:.2f}s | HISTORY: {hist_time:.2f}s | TOTAL: {total_time:.2f}s")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    args = parse_args(argv)
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
