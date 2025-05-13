# modules/scan.py
import os, json, shutil
from pathlib import Path
from datetime import datetime
import csv
from tqdm import tqdm
from flask import current_app
from multiprocessing import Value
from time import time

# Shared variables
SCAN_PROGRESS = Value("i", 0)
is_canceled = False

def get_array_drives():
    return sorted(
        str(p) for p in Path("/mnt").glob("disk*")
        if p.is_dir() and not str(p).startswith("/mnt/disks")
    )

def get_pool_drives():
    excluded_mounts = {"addons", "remotes", "rootshare", "user", "user0", "disks"}
    return sorted(
        str(p) for p in Path("/mnt").iterdir()
        if p.is_dir() and not p.name.startswith("disk") and p.name not in excluded_mounts
    )

def clean_old_csv_files(directory, keep_count=5):
    csv_files = sorted(
        Path(directory).glob("duplicates_*.csv"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    for old_file in csv_files[keep_count:]:
        try:
            old_file.unlink()
            print(f"Deleted old CSV file: {old_file}")
        except Exception as e:
            print(f"Error deleting file {old_file}: {e}")

def format_size(size_in_bytes):
    units = ["bytes", "KB", "MB", "GB", "TB", "PB"]
    size = size_in_bytes
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:,.2f} {units[unit_index]}"

def scan_for_duplicates(selected_disks, min_size=None, ext_filter=None, keep_strategy_order=None, app=None):
    session_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    global is_canceled
    is_canceled = False

    start_time = time()

    if app:
        with app.app_context():
            static_dir = os.path.join(current_app.root_path, "static", "output")
            scan_output_dir = os.path.join(static_dir, "scan_results")
            try:
                os.makedirs(scan_output_dir, exist_ok=True)
            except Exception as e:
                print(f"Error creating output directory {scan_output_dir}: {e}")
                return None
    else:
        raise RuntimeError("Application context is required to run this function.")

    file_index = {}
    total_files = sum(len(files) for disk in selected_disks for _, _, files in os.walk(disk))
    processed_files = 0

    with SCAN_PROGRESS.get_lock():
        SCAN_PROGRESS.value = 0

    if total_files == 0:
        SCAN_PROGRESS.value = 100
        print("No files found to scan.")
        return None

    total_duplicate_files = 0
    total_duplicate_size = 0
    disks_with_duplicates = set()
    drive_summary = {}

    def get_drive_free_space(path):
        """Helper function to get the available space on a drive."""
        try:
            total, used, free = shutil.disk_usage(path)
            return free
        except Exception as e:
            print(f"Error getting free space for {path}: {e}")
            return 0

    def sort_by_strategy(paths, strategy):
        """Sort paths based on a single strategy."""
        if strategy == "newest":
            return sorted(paths, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
        elif strategy == "oldest":
            return sorted(paths, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else float("inf"))
        elif strategy == "largest":
            return sorted(paths, key=lambda p: os.path.getsize(p) if os.path.exists(p) else 0, reverse=True)
        elif strategy == "smallest":
            return sorted(paths, key=lambda p: os.path.getsize(p) if os.path.exists(p) else float("inf"))
        elif strategy == "least_space":
            return sorted(paths, key=lambda p: get_drive_free_space(os.path.dirname(p)), reverse=False)
        elif strategy == "most_space":
            return sorted(paths, key=lambda p: get_drive_free_space(os.path.dirname(p)), reverse=True)
        return paths

    with tqdm(total=total_files, desc="Scanning files", unit="file") as pbar:
        for disk in selected_disks:
            for root, _, files in os.walk(disk):
                if is_canceled:
                    print("Scan canceled.")
                    return None
                for file in files:
                    if is_canceled:
                        print("Scan canceled.")
                        return None
                    file_path = os.path.join(root, file)

                    if not os.path.isfile(file_path):
                        print(f"Skipping non-file: {file_path}")
                        continue

                    try:
                        if min_size and os.path.getsize(file_path) < min_size:
                            continue
                        if ext_filter and "*" not in ext_filter:
                            if not any(file.lower().endswith(ext.lower()) for ext in ext_filter):
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

    if is_canceled:
        print("Scan canceled after file walk.")
        return None

    csv_file = Path(scan_output_dir) / f"duplicates_{session_timestamp}.csv"
    group_id = 1
    duplicates_found = False

    for rel_path, paths in file_index.items():
        if len(paths) > 1:
            if not duplicates_found:
                # Only open and write the CSV header if we find the first duplicate group
                f = open(csv_file, "w", newline="")
                writer = csv.writer(f)
                writer.writerow(["Group", "Relative Path", "Full Path", "Modification Time", "Size", "Keep"])
                duplicates_found = True
            try:
                # Apply strategies in the specified order
                for strategy in keep_strategy_order:
                    paths = sort_by_strategy(paths, strategy)
            except Exception as e:
                print(f"Error sorting paths for {rel_path}: {e}")
                continue

            for path in paths:
                if not os.path.exists(path):
                    continue
                try:
                    parts = os.path.normpath(path).split(os.sep)
                    drive = parts[2] if len(parts) > 2 else "unknown"
                    disks_with_duplicates.add(drive)
                    if path != paths[0]:
                        drive_summary.setdefault(drive, {"file_count": 0, "total_size": 0})
                        drive_summary[drive]["file_count"] += 1
                        drive_summary[drive]["total_size"] += os.path.getsize(path)
                        total_duplicate_files += 1
                        total_duplicate_size += os.path.getsize(path)

                    mod_time = os.path.getmtime(path)
                    size = os.path.getsize(path)
                    keep = "yes" if path == paths[0] else "no"
                    writer.writerow([group_id, rel_path, path, mod_time, size, keep])
                except Exception as e:
                    print(f"Error writing data for {path}: {e}")
            group_id += 1

    if duplicates_found:
        f.close()

    if total_duplicate_files == 0:
        print("No duplicate files found. Returning empty summary.")
        with SCAN_PROGRESS.get_lock():
            SCAN_PROGRESS.value = 100
        return {
            "csv_file": None,
            "total_duplicates": "0",
            "disks_with_duplicates": [],
            "total_duplicate_size": "0.00 MB",
            "drive_summary": {},
            "time_taken": float(time() - start_time),
            "time_completed": datetime.now().strftime("%m/%d/%Y %I:%M:%S %p"),
        }

    clean_old_csv_files(scan_output_dir, keep_count=5)
    time_taken = time() - start_time

    formatted_size = format_size(total_duplicate_size)
    for drive in drive_summary:
        drive_summary[drive]["total_size"] = format_size(drive_summary[drive]["total_size"])

    with SCAN_PROGRESS.get_lock():
        SCAN_PROGRESS.value = 100
        print("✅ Duplicate detection complete. Results saved to:", csv_file)

    summary = {
        "csv_file": str(csv_file),
        "total_duplicates": f"{total_duplicate_files:,}",
        "disks_with_duplicates": list(disks_with_duplicates),
        "total_duplicate_size": formatted_size,
        "drive_summary": drive_summary,
        "time_taken": float(time_taken),
        "time_completed": datetime.now().strftime("%m/%d/%Y %I:%M:%S %p"),
    }

    # Write summary JSON file
    json_file = Path(scan_output_dir) / f"duplicates_{session_timestamp}.json"
    try:
        with open(json_file, "w") as jf:
            json.dump(summary, jf, indent=2)
        print("✅ Scan summary JSON saved to:", json_file)
    except Exception as e:
        print(f"Error writing JSON summary: {e}")

    return summary
