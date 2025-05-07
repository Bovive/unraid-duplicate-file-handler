# modules/scan.py
import os
from pathlib import Path
from datetime import datetime
import csv
from tqdm import tqdm
from flask import current_app
from multiprocessing import Value

SESSION_TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# Use a global variable for thread-safe progress tracking
SCAN_PROGRESS = Value("i", 0)  # Shared integer initialized to 0

def get_array_drives():
    """Get list of mounted array drives under /mnt/diskX (excluding cache and parity)."""
    return sorted(str(p) for p in Path("/mnt").glob("disk*") if p.is_dir())

def get_pool_drives():
    """Get list of mounted pool drives under /mnt (e.g., /mnt/cache, /mnt/poolname)."""
    system_mounts = {"user", "user0", "disks"}
    return sorted(
        str(p) for p in Path("/mnt").iterdir()
        if p.is_dir() and not p.name.startswith("disk") and p.name not in system_mounts
    )

def scan_for_duplicates(selected_disks, min_size=None, ext_filter=None, keep_strategy="newest", app=None):
    """Scan the selected drives for duplicates and calculate metrics."""
    # Push the application context if provided
    if app:
        with app.app_context():
            # Use the /static/output directory
            static_dir = os.path.join(current_app.root_path, "static", "output")
            scan_output_dir = os.path.join(static_dir, "scan_results")
            try:
                os.makedirs(scan_output_dir, exist_ok=True)
            except Exception as e:
                print(f"Error creating output directory {scan_output_dir}: {e}")
                return
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
        # If no files are found, set progress to 100% and return
        with SCAN_PROGRESS.get_lock():
            SCAN_PROGRESS.value = 100
        print("No files found to scan.")
        return

    with tqdm(total=total_files, desc="Scanning files", unit="file") as pbar:
        for disk in selected_disks:
            for root, _, files in os.walk(disk):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        # Apply filters
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
    with SCAN_PROGRESS.get_lock():
        SCAN_PROGRESS.value = 100
        print("Scan complete. Progress set to 100%.")

    print(f"✅ Duplicate detection complete. Results saved to: {csv_file}")
    return {
        "csv_file": str(csv_file),
        "total_duplicates": total_duplicate_files,
        "disks_with_duplicates": list(disks_with_duplicates),
        "total_duplicate_size": total_duplicate_size,
    }
