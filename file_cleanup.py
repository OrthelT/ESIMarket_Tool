import os
import shutil
from logging import getLogger

logger = getLogger(__name__)

def rename_move_and_archive_csv(src_folder, latest_folder, archive_folder, full_cleanup, latest_only=False):
    # Find all files matching the pattern 'valemarketstats_*.csv' in the source folder
    csv_files = [f for f in os.listdir(src_folder) if f.startswith("marketstats_") and f.endswith(".csv")]
    other_csv_files = [f for f in os.listdir(src_folder) if f.endswith(".csv")]

    if not csv_files:
        print("No matching CSV files found.")
        return

    # Sort the files by their modified time to get the latest one
    csv_files.sort(key=lambda f: os.path.getmtime(os.path.join(src_folder, f)), reverse=True)
    latest_file = csv_files[0]
    print(latest_file)
    # Define the source path for the latest file
    latest_file_path = os.path.join(src_folder, latest_file)
    print(latest_file_path)
    # Define the destination path for the new file
    new_file_name = "marketstats_latest.csv"
    latest_file_dest = os.path.join(latest_folder, new_file_name)

    history_folder = f"{src_folder}/markethistory"

    # Create the 'latest' and 'archive' folders if they don't exist
    os.makedirs(latest_folder, exist_ok=True)
    os.makedirs(archive_folder, exist_ok=True)
    os.makedirs(history_folder, exist_ok=True)

    # Copy the latest file to the 'latest' folder with the new name
    shutil.copy(latest_file_path, latest_file_dest)

    logger.info(f"File '{latest_file}' has been copied and renamed to '{new_file_name}' in the '{latest_folder}' folder.")

    # Move the rest of the files to the archive folder
    full_cleanup = full_cleanup

    if full_cleanup:

        for file in other_csv_files[1:]:
            if file.startswith("markethistory"):
                shutil.move(os.path.join(src_folder, file), os.path.join(history_folder, file))
                print(f"File '{file}' has been moved to the '{history_folder}' folder.")
            else:
                file_path = os.path.join(src_folder, file)
                archive_file_dest = os.path.join(archive_folder, file)
                shutil.move(file_path, archive_file_dest)
                print(f"File '{file}' has been moved to the '{archive_folder}' folder.")
        src_folder_files = [file for file in os.listdir(src_folder) if file.endswith(".csv")]
        for file in src_folder_files:
            file_path = os.path.join(src_folder, file)
            os.remove(file_path)
            print(f"File '{file}' has been removed.")

    if latest_only:
        old_files = [f for f in os.listdir(archive_folder) if f.endswith(".csv")]
        for file in old_files[1:]:
            file_path = os.path.join(archive_folder, file)
            os.remove(file_path)
            print(f"File '{file}' has been removed.")

if __name__ == "__main__":
    pass