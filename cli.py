"""
CLI entry point and main orchestration for ESI Market Tool.

Supports interactive mode (-i), headless mode (--headless), and default pipeline.
"""

import argparse
import asyncio
import csv as csv_mod
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from cache import HistoryCache
from config import load_config, check_env_file, ConfigurationError, AppConfig
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
console = Console()


def _handle_config_error(error: ConfigurationError, headless: bool) -> None:
    """Handle missing/invalid config: offer setup wizard or exit."""
    if headless:
        console.print(f"\n[red]Configuration error:[/] {error}")
        console.print("Run interactively first to configure: uv run esi-market")
        sys.exit(1)
    console.print()
    console.print(Panel(
        "[bold]Welcome to ESI Market Tool![/bold]\n\n"
        "  Looks like this is your first run.\n"
        "  Let's get you set up.",
        border_style="blue",
    ))
    console.print()
    launch = Prompt.ask(
        "Launch the setup wizard?",
        choices=["y", "n"],
        default="y",
    )
    if launch == "y":
        import subprocess
        subprocess.run([sys.executable, "setup.py"])
    sys.exit(0)


def _check_credentials(client_id: str | None, secret_key: str | None, headless: bool) -> None:
    """Guard against None credentials after loading .env."""
    if not client_id or not secret_key:
        error = ConfigurationError(
            "EVE API credentials (CLIENT_ID / SECRET_KEY) are missing or empty in .env file."
        )
        _handle_config_error(error, headless)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog='esi-market',
        description='ESI Structure Market Tools for Eve Online',
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run without prompts (standard mode, CSV output, no interactive input)',
    )
    parser.add_argument(
        '-i', '--interactive',
        action='store_true',
        help='Show interactive menu before running',
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


# -----------------------------------------------
# Shared helpers
# -----------------------------------------------

async def _load_type_ids_and_names_async(
    config: AppConfig,
    esi: ESIClient,
) -> tuple[list[int], dict[int, str]]:
    """Read type IDs from CSV, resolve any missing names via ESI.

    Returns (type_ids, type_names dict).
    """
    type_ids_path = config.resolve_path(config.paths.data.type_ids)
    type_ids_df = pd.read_csv(type_ids_path)
    id_col = None
    for col in ('type_ids', 'type_id', 'typeID'):
        if col in type_ids_df.columns:
            id_col = col
            type_ids = type_ids_df[col].tolist()
            break
    else:
        logger.error(f"No recognized type_id column in {type_ids_path}")
        sys.exit(1)

    # Build type_names dict from CSV, resolve any missing via ESI
    type_names: dict[int, str] = {}
    if 'type_name' in type_ids_df.columns:
        for _, row in type_ids_df.iterrows():
            name = str(row.get('type_name', '')).strip()
            if name and name != 'nan':
                type_names[int(row[id_col])] = name

    missing_names = [tid for tid in type_ids if tid not in type_names]
    if missing_names:
        logger.info(f"Resolving {len(missing_names)} item names from ESI...")
        resolved = await esi.fetch_sde_names(missing_names)
        type_names.update(resolved)
        # Persist resolved names back to CSV
        type_ids_path.parent.mkdir(parents=True, exist_ok=True)
        with open(type_ids_path, 'w', newline='') as f:
            writer = csv_mod.writer(f)
            writer.writerow(['type_ids', 'type_name'])
            for tid in sorted(set(type_ids)):
                writer.writerow([tid, type_names.get(tid, '')])
        logger.info(f"Updated {type_ids_path} with {len(resolved)} item names")

    return type_ids, type_names


# -----------------------------------------------
# Sub-pipeline functions
# -----------------------------------------------

async def _fetch_and_export_orders(
    esi: ESIClient,
    config: AppConfig,
    progress: Progress,
    output_dir: Path,
    latest_dir: Path,
) -> tuple[list[dict], float]:
    """Fetch market orders, save CSV. Returns (orders_data, elapsed_seconds)."""
    with progress:
        orders_result = await esi.fetch_market_orders(
            structure_id=config.esi.structure_id,
            progress=progress,
        )

    market_orders = orders_result.data
    mkt_time = orders_result.elapsed_seconds
    avg_time = (mkt_time * 1000 / len(market_orders)) if market_orders else 0
    logger.info(f"Market orders: {mkt_time:.2f}s, avg: {avg_time:.2f}ms")

    save_orders_csv(market_orders, output_dir)
    return market_orders, mkt_time


async def _fetch_and_export_history(
    esi: ESIClient,
    config: AppConfig,
    progress: Progress,
    type_ids: list[int],
    type_names: dict[int, str],
    output_dir: Path,
    latest_dir: Path,
    history_cache: HistoryCache | None,
) -> tuple[pd.DataFrame, float, 'FetchResult']:
    """Fetch market history, save CSV. Returns (history_df, elapsed_seconds, result)."""
    from esi_client import FetchResult  # noqa: F811

    with progress:
        history_result = await esi.fetch_market_history(
            region_id=config.esi.region_id,
            type_ids=type_ids,
            progress=progress,
            type_names=type_names,
        )
    historical_df = pd.DataFrame(history_result.data)
    hist_time = history_result.elapsed_seconds

    if history_cache:
        history_cache.save()

    save_history_csv(historical_df, output_dir)
    return historical_df, hist_time, history_result


# -----------------------------------------------
# Full pipeline
# -----------------------------------------------

async def run(args: argparse.Namespace) -> None:
    """Main orchestration: load config, authenticate, fetch, process, export."""
    global logger

    # 1. Load config
    try:
        config = load_config()
        check_env_file(config.project_root)
    except ConfigurationError as e:
        _handle_config_error(e, args.headless)

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
    _check_credentials(client_id, secret_key, args.headless)

    # 4. Output directory (CLI flag > config > default)
    if args.output_dir:
        output_dir = config.resolve_path(args.output_dir)
    else:
        output_dir = config.resolve_path(config.paths.output_dir)
    latest_dir = output_dir / 'latest'
    latest_dir.mkdir(parents=True, exist_ok=True)

    # 5. Authenticate (sync — runs before async event loop is busy)
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
        print("Run interactively first: uv run esi-market")
        sys.exit(1)

    rate_limiter = TokenBucketRateLimiter(
        burst_size=config.rate_limiting.burst_size,
        tokens_per_second=config.rate_limiting.tokens_per_second,
    )

    # Load history cache for conditional requests
    history_cache = None
    if config.caching.enabled:
        cache_path = config.resolve_path(config.caching.cache_file)
        history_cache = HistoryCache(cache_path)
        history_cache.load()

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        disable=args.headless,
    )

    async with ESIClient(config=config, token=token, rate_limiter=rate_limiter, history_cache=history_cache) as esi:
        start_time = datetime.now()
        logger.info(f"Run started at {start_time}")

        # Fetch market orders
        market_orders, mkt_time = await _fetch_and_export_orders(
            esi, config, progress, output_dir, latest_dir,
        )

        # Read type IDs and resolve names
        type_ids, type_names = await _load_type_ids_and_names_async(config, esi)

        # Fetch market history
        historical_df, hist_time, history_result = await _fetch_and_export_history(
            esi, config, progress, type_ids, type_names,
            output_dir, latest_dir, history_cache,
        )

        # Process data
        orders_df = pd.DataFrame(market_orders)
        filtered = filter_orders(type_ids, orders_df)
        sell_agg = aggregate_sell_orders(filtered)
        final_data = merge_market_stats(sell_agg, historical_df, type_names)
        with_jita = await get_jita_prices(final_data, session=esi._session, user_agent=ua_string)

    # Save files
    logger.info("Saving CSV files...")
    save_stats_csv(final_data, output_dir)

    # File cleanup: copy latest, archive old files
    src_folder = str(output_dir)
    latest_folder = str(latest_dir)
    archive_folder = str(output_dir / 'archive')
    rename_move_and_archive_csv(src_folder, latest_folder, archive_folder, "archive")

    save_jita_csv(with_jita, latest_dir)

    # Google Sheets
    sheets_updated = False
    if config.google_sheets.enabled and not args.no_sheets:
        creds_path = config.resolve_path(config.google_sheets.credentials_file)
        if not creds_path.exists():
            logger.warning(f"Google Sheets credentials not found: {creds_path}")
            print("Google Sheets is enabled but not configured. Run 'uv run esi-setup' to set up credentials.")
        else:
            try:
                logger.info("Updating Google Sheets...")
                update_all_google_sheets(config)
                logger.info("Google Sheets updated successfully")
                sheets_updated = True
            except Exception as e:
                logger.error(f"Failed to update Google Sheets: {e}")
                print(f"Google Sheets update failed: {e}")

    # Summary
    total_time = (datetime.now() - start_time).total_seconds()

    print("=" * 80)
    print("ESI Request Completed Successfully.")
    print(f"Data for {len(final_data)} items retrieved.")
    if history_cache and config.caching.enabled:
        hits = history_result.cache_hits
        fetched = len(type_ids) - hits - len(history_result.failed_items)
        print(f"Cache: {hits} unchanged (304), {fetched} updated (200), "
              f"{len(history_result.failed_items)} failed")
        logger.info(f"Cache stats: {hits} hits, {fetched} fetched, "
                     f"{len(history_result.failed_items)} failed")
    if sheets_updated:
        print("Google Sheets updated successfully.")
    print("-" * 80)

    logger.info(f"MARKET ORDERS: {mkt_time:.2f}s | HISTORY: {hist_time:.2f}s | TOTAL: {total_time:.2f}s")


# -----------------------------------------------
# Interactive mode
# -----------------------------------------------

async def _interactive_run(args: argparse.Namespace) -> None:
    """Interactive mode: show menu, run selected pipeline."""
    global logger

    # 1. Load config
    try:
        config = load_config()
        check_env_file(config.project_root)
    except ConfigurationError as e:
        _handle_config_error(e, headless=False)

    # 2. Setup logging
    logger = setup_logging(
        log_name='market_structures',
        verbose_console_logging=config.logging.verbose_console_logging,
    )

    ua_string = config.user_agent.format_header()

    # Read type IDs for display
    type_ids_path = config.resolve_path(config.paths.data.type_ids)
    try:
        type_ids_df = pd.read_csv(type_ids_path)
        for col in ('type_ids', 'type_id', 'typeID'):
            if col in type_ids_df.columns:
                item_count = len(type_ids_df)
                break
        else:
            item_count = 0
    except Exception:
        item_count = 0

    while True:
        # Show config summary
        console.print()
        console.print(Panel(
            f"[bold]ESI Market Tool[/bold] - Interactive Mode\n\n"
            f"  Structure: [cyan]{config.esi.structure_id}[/]\n"
            f"  Region:    [cyan]{config.esi.region_id}[/]\n"
            f"  Items:     [cyan]{item_count}[/]\n"
            f"  Caching:   [cyan]{'On' if config.caching.enabled else 'Off'}[/]",
            border_style="blue",
        ))
        console.print()

        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("Key", style="bold cyan", width=4, justify="center")
        menu.add_column("Option", style="white")
        menu.add_row("[1]", "Run full pipeline (orders + history + export)")
        menu.add_row("[2]", "Run orders only (fetch + export orders CSV)")
        menu.add_row("[3]", "Run history only (fetch + export history CSV)")
        menu.add_row("[4]", "View current config")
        menu.add_row("[q]", "Exit")
        console.print(menu)
        console.print()

        choice = Prompt.ask(
            "[bold]Select an option[/]",
            choices=["1", "2", "3", "4", "q", "Q"],
            show_choices=False,
        ).lower()

        if choice == "q":
            console.print("Exiting.")
            return

        if choice == "4":
            console.print(Panel(
                f"[bold]Current Configuration[/bold]\n\n"
                f"  Structure ID:  [cyan]{config.esi.structure_id}[/]\n"
                f"  Region ID:     [cyan]{config.esi.region_id}[/]\n"
                f"  Items tracked: [cyan]{item_count}[/]\n"
                f"  Caching:       [cyan]{'Enabled' if config.caching.enabled else 'Disabled'}[/]\n"
                f"  Cache file:    [cyan]{config.caching.cache_file}[/]\n"
                f"  Output dir:    [cyan]{config.paths.output_dir}[/]\n"
                f"  Google Sheets: [cyan]{'Enabled' if config.google_sheets.enabled else 'Disabled'}[/]\n"
                f"  User-Agent:    [cyan]{ua_string}[/]",
                border_style="blue",
            ))
            Prompt.ask("\n[dim]Press Enter to continue[/]", default="")
            continue

        # For options 1-3, we need to authenticate and set up the client
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        load_dotenv(dotenv_path=config.project_root / '.env')
        client_id = os.getenv('CLIENT_ID')
        secret_key = os.getenv('SECRET_KEY')
        _check_credentials(client_id, secret_key, headless=False)

        SCOPE = ['esi-markets.structure_markets.v1']
        from ESI_OAUTH_FLOW import get_token
        token = get_token(
            client_id=client_id,
            secret_key=secret_key,
            requested_scope=SCOPE,
            user_agent=ua_string,
        )
        if token is None:
            console.print("[red]Authentication failed.[/]")
            continue

        if args.output_dir:
            output_dir = config.resolve_path(args.output_dir)
        else:
            output_dir = config.resolve_path(config.paths.output_dir)
        latest_dir = output_dir / 'latest'
        latest_dir.mkdir(parents=True, exist_ok=True)

        rate_limiter = TokenBucketRateLimiter(
            burst_size=config.rate_limiting.burst_size,
            tokens_per_second=config.rate_limiting.tokens_per_second,
        )

        history_cache = None
        if config.caching.enabled:
            cache_path = config.resolve_path(config.caching.cache_file)
            history_cache = HistoryCache(cache_path)
            history_cache.load()

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        )

        async with ESIClient(config=config, token=token, rate_limiter=rate_limiter, history_cache=history_cache) as esi:
            start_time = datetime.now()

            if choice == "1":
                # Full pipeline
                market_orders, mkt_time = await _fetch_and_export_orders(
                    esi, config, progress, output_dir, latest_dir,
                )
                type_ids, type_names = await _load_type_ids_and_names_async(config, esi)
                historical_df, hist_time, history_result = await _fetch_and_export_history(
                    esi, config, progress, type_ids, type_names,
                    output_dir, latest_dir, history_cache,
                )

                orders_df = pd.DataFrame(market_orders)
                filtered = filter_orders(type_ids, orders_df)
                sell_agg = aggregate_sell_orders(filtered)
                final_data = merge_market_stats(sell_agg, historical_df, type_names)
                with_jita = await get_jita_prices(final_data, session=esi._session, user_agent=ua_string)

                save_stats_csv(final_data, output_dir)
                src_folder = str(output_dir)
                latest_folder = str(latest_dir)
                archive_folder = str(output_dir / 'archive')
                rename_move_and_archive_csv(src_folder, latest_folder, archive_folder, "archive")
                save_jita_csv(with_jita, latest_dir)

                if not args.no_sheets and config.google_sheets.enabled:
                    creds_path = config.resolve_path(config.google_sheets.credentials_file)
                    if creds_path.exists():
                        try:
                            update_all_google_sheets(config)
                            console.print("[green]Google Sheets updated.[/]")
                        except Exception as e:
                            console.print(f"[red]Google Sheets failed: {e}[/]")

                total = (datetime.now() - start_time).total_seconds()
                console.print(f"\n[green]Full pipeline complete.[/] {len(final_data)} items, {total:.1f}s")
                if history_cache and config.caching.enabled:
                    hits = history_result.cache_hits
                    fetched = len(type_ids) - hits - len(history_result.failed_items)
                    console.print(f"Cache: {hits} unchanged (304), {fetched} updated (200), "
                                  f"{len(history_result.failed_items)} failed")

            elif choice == "2":
                # Orders only
                market_orders, mkt_time = await _fetch_and_export_orders(
                    esi, config, progress, output_dir, latest_dir,
                )
                src_folder = str(output_dir)
                latest_folder = str(latest_dir)
                archive_folder = str(output_dir / 'archive')
                rename_move_and_archive_csv(src_folder, latest_folder, archive_folder, "archive")

                total = (datetime.now() - start_time).total_seconds()
                console.print(f"\n[green]Orders complete.[/] {len(market_orders)} orders, {total:.1f}s")

            elif choice == "3":
                # History only
                type_ids, type_names = await _load_type_ids_and_names_async(config, esi)
                historical_df, hist_time, history_result = await _fetch_and_export_history(
                    esi, config, progress, type_ids, type_names,
                    output_dir, latest_dir, history_cache,
                )
                src_folder = str(output_dir)
                latest_folder = str(latest_dir)
                archive_folder = str(output_dir / 'archive')
                rename_move_and_archive_csv(src_folder, latest_folder, archive_folder, "archive")

                total = (datetime.now() - start_time).total_seconds()
                console.print(f"\n[green]History complete.[/] {len(historical_df)} records, {total:.1f}s")
                if history_cache and config.caching.enabled:
                    hits = history_result.cache_hits
                    fetched = len(type_ids) - hits - len(history_result.failed_items)
                    console.print(f"Cache: {hits} unchanged (304), {fetched} updated (200), "
                                  f"{len(history_result.failed_items)} failed")

        Prompt.ask("\n[dim]Press Enter to continue[/]", default="")


# -----------------------------------------------
# Entry point
# -----------------------------------------------

def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    args = parse_args(argv)
    if args.headless:
        asyncio.run(run(args))
    else:
        asyncio.run(_interactive_run(args))


if __name__ == '__main__':
    main()
