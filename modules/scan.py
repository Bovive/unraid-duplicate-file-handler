# modules/scan.py
import os
from pathlib import Path
from datetime import datetime
import csv
from tqdm import tqdm
from flask import current_app
from multiprocessing import Value
from time import time

SESSION_TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# Use a global variable for thread-safe progress tracking
SCAN_PROGRESS = Value("i", 0)  # Shared integer initialized to 0

def get_array_drives():
    """Get list of mounted array drives under /mnt/diskX (excluding /mnt/disks)."""
    return sorted(
        str(p) for p in Path("/mnt").glob("disk*") 
        if p.is_dir() and not str(p).startswith("/mnt/disks")
    )

def get_pool_drives():
    """Get list of mounted pool drives under /mnt (excluding /mnt/addons, /mnt/remotes, and /mnt/rootshare)."""
    excluded_mounts = {"addons", "remotes", "rootshare", "user", "user0", "disks"}
    return sorted(
        str(p) for p in Path("/mnt").iterdir()
        if p.is_dir() and not p.name.startswith("disk") and p.name not in excluded_mounts
    )

def clean_old_csv_files(directory, keep_count=5):
    """Keep only the latest `keep_count` CSV files in the specified directory."""
    csv_files = sorted(
        Path(directory).glob("duplicates_*.csv"),
        key=lambda f: f.stat().st_mtime,  # Sort by modification time
        reverse=True,  # Newest files first
    )
    for old_file in csv_files[keep_count:]:  # Skip the latest `keep_count` files
        try:
            old_file.unlink()  # Delete the file
            print(f"Deleted old CSV file: {old_file}")
        except Exception as e:
            print(f"Error deleting file {old_file}: {e}")

def format_size(size_in_bytes):
    """Format the size in bytes into a human-readable string with commas and appropriate units."""
    units = ["bytes", "KB", "MB", "GB", "TB", "PB"]
    size = size_in_bytes
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    # Format the size with commas and two decimal places
    return f"{size:,.2f} {units[unit_index]}"

def scan_for_duplicates(selected_disks, min_size=None, ext_filter=None, keep_strategy="newest", app=None):
    """Scan the selected drives for duplicates and calculate metrics."""
    start_time = time()  # Track the start time

    if app:
        with app.app_context():
            static_dir = os.path.join(current_app.root_path, "static", "output")
            scan_output_dir = os.path.join(static_dir, "scan_results")
            try:
                os.makedirs(scan_output_dir, exist_ok=True)
            except Exception as e:
                print(f"Error creating output directory {scan_output_dir}: {e}")
                return {
                    "csv_file": None,
                    "total_duplicates": 0,
                    "disks_with_duplicates": [],
                    "total_duplicate_size": 0,
                    "time_taken": 0,
                    "time_completed": datetime.now().strftime("%m/%d/%Y %I:%M:%S %p"),
                }
    else:
        raise RuntimeError("Application context is required to run this function.")

    file_index = {}
    total_files = sum(len(files) for disk in selected_disks for _, _, files in os.walk(disk))
    total_duplicate_files = 0
    total_duplicate_size = 0
    disks_with_duplicates = set()

    # Initialize progress tracking
    with SCAN_PROGRESS.get_lock():
        SCAN_PROGRESS.value = 0
    processed_files = 0

    if total_files == 0:
        with SCAN_PROGRESS.get_lock():
            SCAN_PROGRESS.value = 100
        print("No files found to scan.")
        return {
            "csv_file": None,
            "total_duplicates": 0,
            "disks_with_duplicates": [],
            "total_duplicate_size": 0,
            "time_taken": 0,
            "time_completed": datetime.now().strftime("%m/%d/%Y %I:%M:%S %p"),
        }

    with tqdm(total=total_files, desc="Scanning files", unit="file") as pbar:
        for disk in selected_disks:
            for root, _, files in os.walk(disk):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        if min_size and os.path.getsize(file_path) < min_size:
                            continue
                        if ext_filter and not any(file.endswith(ext) for ext in ext_filter):
                            continue

                        rel_path = os.path.relpath(file_path, disk)
                        file_index.setdefault(rel_path, []).append(file_path)
                    except Exception as e:
                        print(f"Error processing {file_path}: {e}")
                    finally:
                        processed_files += 1
                        with SCAN_PROGRESS.get_lock():
                            SCAN_PROGRESS.value = int((processed_files / total_files) * 100)
                        pbar.update(1)

    csv_file = Path(scan_output_dir) / f"duplicates_{SESSION_TIMESTAMP}.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Group", "Relative Path", "Full Path", "Modification Time", "Size", "Keep"])
        group_id = 1
        for rel_path, paths in file_index.items():
            if len(paths) > 1:
                try:
                    if keep_strategy == "newest":
                        paths.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
                    elif keep_strategy == "oldest":
                        paths.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else float("inf"))
                    elif keep_strategy == "largest":
                        paths.sort(key=lambda p: os.path.getsize(p) if os.path.exists(p) else 0, reverse=True)
                    elif keep_strategy == "smallest":
                        paths.sort(key=lambda p: os.path.getsize(p) if os.path.exists(p) else float("inf"))
                except Exception as e:
                    print(f"Error sorting paths for {rel_path}: {e}")
                    continue

                total_duplicate_files += len(paths) - 1
                total_duplicate_size += sum(os.path.getsize(p) for p in paths[1:] if os.path.exists(p))
                disks_with_duplicates.update(os.path.dirname(p).split("/")[2] for p in paths if os.path.exists(p))

                for path in paths:
                    if not os.path.exists(path):
                        continue
                    try:
                        mod_time = os.path.getmtime(path)
                        size = os.path.getsize(path)
                        keep = "yes" if path == paths[0] else "no"
                        writer.writerow([group_id, rel_path, path, mod_time, size, keep])
                    except Exception as e:
                        print(f"Error writing data for {path}: {e}")
                group_id += 1

    # Clean up old CSV files
    clean_old_csv_files(scan_output_dir, keep_count=5)

    end_time = time()  # Track the end time
    time_taken = end_time - start_time  # Calculate time taken

    # Format total duplicate size using the helper function
    formatted_size = format_size(total_duplicate_size)

    with SCAN_PROGRESS.get_lock():
        SCAN_PROGRESS.value = 100
        print("Scan complete. Progress set to 100%.")

    print(f"✅ Duplicate detection complete. Results saved to: {csv_file}")
    return {
        "csv_file": str(csv_file) if csv_file else None,  # Convert Path object to string
        "total_duplicates": f"{total_duplicate_files:,}",  # Add commas to the number
        "disks_with_duplicates": list(disks_with_duplicates),  # Ensure it's a list
        "total_duplicate_size": formatted_size,  # Use formatted size
        "time_taken": float(time_taken),  # Ensure it's a float
        "time_completed": datetime.now().strftime("%m/%d/%Y %I:%M:%S %p"),  # Formatted time
    }
