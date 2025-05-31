import os
import shutil
import time
from datetime import datetime
from logging import getLogger

logger = getLogger(__name__)

def remove_old_files(folder_path, days=30):
    """Remove files older than specified days from given folder"""
    current_time = time.time()
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            file_age = current_time - os.path.getmtime(file_path)
            if file_age > (days * 24 * 60 * 60):  # Convert days to seconds
                os.remove(file_path)
                logger.info(f"Removed old file: {filename} (age: {file_age/24/60/60:.1f} days)")

def rename_move_and_archive_csv(src_folder, latest_folder, archive_folder, cleanup_mode = "archive"):

    """
    This function renames the latest file and moves the rest to the archive folder.
    It also removes files older than 30 days from the archive and history folders.
    
    The cleanup_mode parameter can be set to "archive" or "latest_only". 
    Latest_only will remove all but the latest file.
    The default is "archive", which will keep files for up to 30 days. 
    History files are maintained indefinitely or until manually deleted.
    """
    
    print("\n"*2)
    print("="*80)
    print("Cleaning up CSV files")
    print("="*80)
    
    # Create folders if they don't exist
    os.makedirs(latest_folder, exist_ok=True)
    os.makedirs(archive_folder, exist_ok=True)
    history_folder = os.path.join(src_folder, "markethistory")
    os.makedirs(history_folder, exist_ok=True)

    # Find and sort CSV files
    csv_files = [f for f in os.listdir(src_folder) if f.startswith("marketstats_") and f.endswith(".csv")]
    other_csv_files = [f for f in os.listdir(src_folder) if f.endswith(".csv")]

    if not csv_files:
        logger.warning("No matching CSV files found.")
        return

    # Handle latest file
    csv_files.sort(key=lambda f: os.path.getmtime(os.path.join(src_folder, f)), reverse=True)
    latest_file = csv_files[0]
    latest_file_path = os.path.join(src_folder, latest_file)
    new_file_name = "marketstats_latest.csv"
    latest_file_dest = os.path.join(latest_folder, new_file_name)

    # Copy latest file
    shutil.copy(latest_file_path, latest_file_dest)
    logger.info(f"Latest file copied to: {latest_file_dest}")

    history_files = [f for f in other_csv_files if f.startswith("markethistory")]
    history_files.sort(key=lambda f: os.path.getmtime(os.path.join(src_folder, f)), reverse=True)
    latest_history_file = history_files[0]
    latest_history_file_path = os.path.join(src_folder, latest_history_file)
    new_history_file_name = "markethistory_latest.csv"
    latest_history_file_dest = os.path.join(latest_folder, new_history_file_name)
    shutil.copy(latest_history_file_path, latest_history_file_dest)
    logger.info(f"Latest history file copied to: {latest_history_file_dest}")

    if cleanup_mode == "archive":
        # Move files to appropriate folders
        for file in other_csv_files[1:]:
            if file.startswith("markethistory"):
                shutil.move(os.path.join(src_folder, file), os.path.join(history_folder, file))
                logger.info(f"Moved history file to: {history_folder}/{file}")
            else:
                archive_file_dest = os.path.join(archive_folder, file)
                shutil.move(os.path.join(src_folder, file), archive_file_dest)
                logger.info(f"Moved to archive: {file}")
        
        # Clean source folder
        for file in [f for f in os.listdir(src_folder) if f.endswith(".csv")]:
            os.remove(os.path.join(src_folder, file))
            logger.info(f"Removed from source: {file}")
        
        # Remove files older than 30 days from archive and history folders
        logger.info("Removing files older than 30 days from archive folders")
        remove_old_files(archive_folder)

    elif cleanup_mode == "latest_only":
        # Remove all but latest file
        input("Are you sure you want to remove all but the latest file? (y/n)")
        if input == "y":
            for file in [f for f in os.listdir(archive_folder) if f.endswith(".csv")]:
                os.remove(os.path.join(archive_folder, file))
                logger.info(f"Removed from archive: {file}")
        else:
            logger.info("Cleanup cancelled.")

if __name__ == "__main__":
    pass