# modules/scan.py
import os
from pathlib import Path
from datetime import datetime
import csv
from tqdm import tqdm

SESSION_TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def scan_for_duplicates():
    selected_disks = ["/mnt/disk1", "/mnt/disk2"]  # Example disks for now
    min_size = 0
    ext_filter = []
    keep_strategy = "newest"

    # Fixed output directory
    scan_output_dir = "/output/scan_results"
    os.makedirs(scan_output_dir, exist_ok=True)

    file_index = {}
    total_files = sum(len(files) for disk in selected_disks for _, _, files in os.walk(disk))

    with tqdm(total=total_files, desc="Scanning files", unit="file") as pbar:
        for disk in selected_disks:
            for root, _, files in os.walk(disk):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        if min_size and os.path.getsize(file_path) < min_size:
                            pbar.update(1)
                            continue
                        if ext_filter and not file.endswith(tuple(ext_filter)):
                            pbar.update(1)
                            continue

                        rel_path = os.path.relpath(file_path, disk)
                        file_index.setdefault(rel_path, []).append(file_path)
                    except Exception as e:
                        print(f"Error processing {file_path}: {e}")
                    finally:
                        pbar.update(1)

    csv_file = Path(scan_output_dir) / f"duplicates_{SESSION_TIMESTAMP}.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Group", "Relative Path", "Full Path", "Modification Time", "Size", "Keep"])
        group_id = 1
        for rel_path, paths in file_index.items():
            if len(paths) > 1:
                for path in paths:
                    mod_time = os.path.getmtime(path)
                    size = os.path.getsize(path)
                    keep = "yes" if path == paths[0] else "no"
                    writer.writerow([group_id, rel_path, path, mod_time, size, keep])
                group_id += 1

    print(f"✅ Duplicate detection complete. Results saved to: {csv_file}")
