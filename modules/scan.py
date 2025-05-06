# modules/scan.py
import os
from pathlib import Path
from datetime import datetime
import csv
from tqdm import tqdm
from flask import current_app  # For progress tracking

SESSION_TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def get_array_drives():
    """Retrieve all array drives, excluding parity drives."""
    array_drives = []
    disk_cfg_path = "/boot/config/disk.cfg"
    if os.path.exists(disk_cfg_path):
        with open(disk_cfg_path, "r") as f:
            for line in f:
                if line.startswith("disk") and "name" in line:
                    drive_name = line.split("=")[1].strip()
                    if "parity" not in drive_name.lower():  # Exclude parity drives
                        array_drives.append(f"/mnt/{drive_name}")
    return array_drives


def get_pool_drives():
    """Retrieve all pool drives."""
    pool_drives = []
    pool_cfg_path = "/boot/config/pools/"
    if os.path.exists(pool_cfg_path):
        for pool in os.listdir(pool_cfg_path):
            pool_drives.append(f"/mnt/{pool}")
    return pool_drives


def scan_for_duplicates(selected_disks):
    """Scan the selected drives for duplicates and calculate metrics."""
    min_size = 0
    ext_filter = []
    keep_strategy = "newest"

    # Fixed output directory
    scan_output_dir = "/output/scan_results"
    os.makedirs(scan_output_dir, exist_ok=True)

    file_index = {}
    total_files = sum(len(files) for disk in selected_disks for _, _, files in os.walk(disk))
    total_duplicate_files = 0
    total_duplicate_size = 0
    disks_with_duplicates = set()

    # Initialize progress tracking
    current_app.config["SCAN_PROGRESS"] = 0

    with tqdm(total=total_files, desc="Scanning files", unit="file") as pbar:
        for disk in selected_disks:
            for root, _, files in os.walk(disk):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        if min_size and os.path.getsize(file_path) < min_size:
                            pbar.update(1)
                            current_app.config["SCAN_PROGRESS"] += 1
                            continue
                        if ext_filter and not file.endswith(tuple(ext_filter)):
                            pbar.update(1)
                            current_app.config["SCAN_PROGRESS"] += 1
                            continue

                        rel_path = os.path.relpath(file_path, disk)
                        file_index.setdefault(rel_path, []).append(file_path)
                    except Exception as e:
                        print(f"Error processing {file_path}: {e}")
                    finally:
                        pbar.update(1)
                        current_app.config["SCAN_PROGRESS"] += 1

    csv_file = Path(scan_output_dir) / f"duplicates_{SESSION_TIMESTAMP}.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Group", "Relative Path", "Full Path", "Modification Time", "Size", "Keep"])
        group_id = 1
        for rel_path, paths in file_index.items():
            if len(paths) > 1:
                # Determine which file to keep based on the keep_strategy
                if keep_strategy == "newest":
                    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                elif keep_strategy == "oldest":
                    paths.sort(key=lambda p: os.path.getmtime(p))
                elif keep_strategy == "largest":
                    paths.sort(key=lambda p: os.path.getsize(p), reverse=True)
                elif keep_strategy == "smallest":
                    paths.sort(key=lambda p: os.path.getsize(p))

                # Update metrics
                total_duplicate_files += len(paths) - 1  # Exclude the "keep" file
                total_duplicate_size += sum(os.path.getsize(p) for p in paths[1:])  # Size of extra files
                disks_with_duplicates.update(os.path.dirname(p).split("/")[2] for p in paths)  # Extract disk names

                # Write the results to the CSV
                for path in paths:
                    mod_time = os.path.getmtime(path)
                    size = os.path.getsize(path)
                    keep = "yes" if path == paths[0] else "no"
                    writer.writerow([group_id, rel_path, path, mod_time, size, keep])
                group_id += 1

    # Reset progress after completion
    current_app.config["SCAN_PROGRESS"] = 100

    print(f"✅ Duplicate detection complete. Results saved to: {csv_file}")
    return {
        "csv_file": str(csv_file),
        "total_duplicates": total_duplicate_files,
        "disks_with_duplicates": list(disks_with_duplicates),
        "total_duplicate_size": total_duplicate_size,
    }
