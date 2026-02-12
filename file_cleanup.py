"""File management: rename, archive, and clean up CSV output files."""

import shutil
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def remove_old_files(folder_path: str | Path, days: int = 30) -> None:
    """Remove files older than specified days from given folder."""
    folder = Path(folder_path)
    if not folder.exists():
        return
    current_time = time.time()
    cutoff = days * 24 * 60 * 60
    for file_path in folder.iterdir():
        if file_path.is_file():
            age = current_time - file_path.stat().st_mtime
            if age > cutoff:
                file_path.unlink()
                logger.info(f"Removed old file: {file_path.name} (age: {age/86400:.1f} days)")


def rename_move_and_archive_csv(
    src_folder: str | Path,
    latest_folder: str | Path,
    archive_folder: str | Path,
    cleanup_mode: str = "archive",
) -> None:
    """Rename latest files, move the rest to archive.

    Args:
        src_folder: Source directory with raw output CSVs
        latest_folder: Directory for the latest-named copies
        archive_folder: Directory for archived files
        cleanup_mode: "archive" (default) or "latest_only"
    """
    src = Path(src_folder)
    latest = Path(latest_folder)
    archive = Path(archive_folder)

    print("\n\n" + "=" * 80)
    print("Cleaning up CSV files")
    print("=" * 80)

    latest.mkdir(parents=True, exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)
    history_dir = src / "markethistory"
    history_dir.mkdir(parents=True, exist_ok=True)

    # Find marketstats CSVs
    csv_files = sorted(
        [f for f in src.iterdir() if f.name.startswith("marketstats_") and f.suffix == ".csv"],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    all_csv = [f for f in src.iterdir() if f.suffix == ".csv"]

    if not csv_files:
        logger.warning("No matching CSV files found.")
        return

    # Copy latest marketstats
    latest_stats = csv_files[0]
    shutil.copy(latest_stats, latest / "marketstats_latest.csv")
    logger.info(f"Latest stats copied to: {latest / 'marketstats_latest.csv'}")

    # Copy latest history
    history_files = sorted(
        [f for f in all_csv if f.name.startswith("markethistory")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if history_files:
        shutil.copy(history_files[0], latest / "markethistory_latest.csv")
        logger.info(f"Latest history copied to: {latest / 'markethistory_latest.csv'}")

    # Copy latest marketorders
    orders_files = sorted(
        [f for f in all_csv if f.name.startswith("marketorders")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if orders_files:
        shutil.copy(orders_files[0], latest / "marketorders_latest.csv")
        logger.info(f"Latest orders copied to: {latest / 'marketorders_latest.csv'}")

    if cleanup_mode == "archive":
        for f in all_csv:
            if f.name.startswith("markethistory"):
                dest = history_dir / f.name
                shutil.move(str(f), str(dest))
                logger.info(f"Moved history: {f.name}")
            else:
                dest = archive / f.name
                shutil.move(str(f), str(dest))
                logger.info(f"Archived: {f.name}")

        # Clean remaining CSVs from source
        for f in src.iterdir():
            if f.suffix == ".csv":
                f.unlink()
                logger.info(f"Removed from source: {f.name}")

        # Prune archive
        logger.info("Removing files older than 30 days from archive")
        remove_old_files(archive)

    elif cleanup_mode == "latest_only":
        # Non-interactive: just log instead of prompting
        logger.info("latest_only mode: keeping only latest files, removing archive contents")
        for f in archive.iterdir():
            if f.suffix == ".csv":
                f.unlink()
                logger.info(f"Removed from archive: {f.name}")


if __name__ == "__main__":
    pass
