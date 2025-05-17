import os, csv, json, shutil, sys, re
from datetime import datetime
from flask import current_app
from multiprocessing import Value, Array

# Global progress variable for cleanup actions
CLEANUP_PROGRESS = Value("i", 0)
CURRENT_FILE_PROGRESS = Value("i", 0)
CURRENT_FILE_NAME = Array("c", 256)  # Fixed-length char buffer

def copy_with_progress(src, dst, chunk_size=1024*1024):
    total_size = os.path.getsize(src)
    copied = 0
    with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
        while True:
            chunk = fsrc.read(chunk_size)
            if not chunk:
                break
            fdst.write(chunk)
            copied += len(chunk)
            with CURRENT_FILE_PROGRESS.get_lock():
                CURRENT_FILE_PROGRESS.value = int(copied / total_size * 100)
    shutil.copystat(src, dst)
    os.remove(src)
    with CURRENT_FILE_PROGRESS.get_lock():
        CURRENT_FILE_PROGRESS.value = 0

def clean_old_cleanup_files(directory, keep_count=10):
    # Clean CSV files
    csv_files = sorted(
        [f for f in os.scandir(directory) if f.name.startswith("cleanup_") and f.name.endswith(".csv")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    for old_file in csv_files[keep_count:]:
        try:
            os.remove(old_file.path)
            print(f"Deleted old cleanup CSV file: {old_file.path}")
        except Exception as e:
            print(f"Error deleting cleanup CSV file {old_file.path}: {e}")

    # Clean JSON files
    json_files = sorted(
        [f for f in os.scandir(directory) if f.name.startswith("cleanup_") and f.name.endswith(".json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    for old_file in json_files[keep_count:]:
        try:
            os.remove(old_file.path)
            print(f"Deleted old cleanup JSON file: {old_file.path}")
        except Exception as e:
            print(f"Error deleting cleanup JSON file {old_file.path}: {e}")

def write_cleanup_results(action, original_csv, affected, failed, attempted, operation_type):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base_name = os.path.splitext(os.path.basename(original_csv))[0]
    output_dir = os.path.join(current_app.root_path, "static", "output", "cleanup_results")
    os.makedirs(output_dir, exist_ok=True)
    csv_filename = f"cleanup_{base_name}_{operation_type}_{timestamp}.csv"
    json_filename = f"cleanup_{base_name}_{operation_type}_{timestamp}.json"
    csv_path = os.path.join(output_dir, csv_filename)
    json_path = os.path.join(output_dir, json_filename)

    # Write CSV
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        if operation_type == "delete":
            writer.writerow(["File Path", "Status", "Error"])
            for file_path in attempted:
                if file_path in affected:
                    writer.writerow([file_path, "Deleted", ""])
                else:
                    error_msg = ""
                    for fail in failed:
                        if fail.startswith(file_path):
                            error_msg = fail[len(file_path):].lstrip(": ")
                            break
                    writer.writerow([file_path, "Failed", error_msg])
        elif operation_type == "move":
            writer.writerow(["From", "To", "Status", "Error"])
            for move_info in attempted:
                found = False
                for moved_info in affected:
                    if move_info == moved_info:
                        writer.writerow([move_info["from"], move_info["to"], "Moved", ""])
                        found = True
                        break
                if not found:
                    error_msg = ""
                    for fail in failed:
                        if fail.startswith(move_info["from"]):
                            error_msg = fail[len(move_info["from"]):].lstrip(": ")
                            break
                    writer.writerow([move_info["from"], move_info["to"], "Failed", error_msg])
        else:
            writer.writerow(["File Path"])  # Always write header

    # Write JSON summary
    summary = {
        "action": action,
        "timestamp": timestamp,
        "original_csv": original_csv,
        "csv_file": csv_filename,
        "total_attempted": len(attempted),
        "total_deleted": len(affected) if operation_type == "delete" else None,
        "total_moved": len(affected) if operation_type == "move" else None,
        "total_failed": len(failed),
        "attempted": attempted,
        "affected": affected,
        "failed": failed,
    }
    with open(json_path, "w") as jf:
        json.dump(summary, jf, indent=2)

    # Clean up old cleanup files (keep only the latest 10)
    clean_old_cleanup_files(output_dir, keep_count=10)

    return csv_filename, json_filename

def delete_duplicates_logic(csv_file):
    if "/" in csv_file or "\\" in csv_file or not csv_file.endswith(".csv"):
        return {"error": "Invalid file name."}, 400

    scan_dir = os.path.join(current_app.root_path, "static", "output", "scan_results")
    csv_path = os.path.join(scan_dir, csv_file)

    if not os.path.isfile(csv_path):
        return {"error": "CSV file not found."}, 404

    scan_root = "/mnt/disk6/storage/"

    deleted = []
    failed = []
    attempted = []
    source_dirs = set()

    # Read all rows first to get total for progress
    with open(csv_path, newline="") as f:
        reader_list = list(csv.DictReader(f))

    file_size_map = {}
    total_size = 0
    for row in reader_list:
        keep = row.get("Keep", "").strip().lower()
        file_path = row.get("Full Path", "").strip()
        if keep != "yes" and file_path:
            with CURRENT_FILE_NAME.get_lock():
                CURRENT_FILE_NAME.value = file_path.encode("utf-8")[:255]
            attempted.append(file_path)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    deleted.append(file_path)
                    source_dirs.add(os.path.dirname(file_path))
                else:
                    failed.append(f"File not found: {file_path}")
            except Exception as e:
                failed.append(f"{file_path}: {e}")
    try:
        # --- Phase 1: File processing (0-85%) ---
        processed_size = 0
        for row in reader_list:
            keep = row.get("Keep", "").strip().lower()
            file_path = row.get("Full Path", "").strip()
            if keep != "yes" and file_path:
                attempted.append(file_path)
                try:
                    if os.path.exists(file_path):
                        # Simulate per-file progress
                        with CURRENT_FILE_PROGRESS.get_lock():
                            CURRENT_FILE_PROGRESS.value = 100
                        os.remove(file_path)
                        deleted.append(file_path)
                        source_dirs.add(os.path.dirname(file_path))

                        with CURRENT_FILE_PROGRESS.get_lock():
                            CURRENT_FILE_PROGRESS.value = 0
                    else:
                        failed.append(f"File not found: {file_path}")
                except Exception as e:
                    failed.append(f"{file_path}: {e}")
                processed_size += file_size_map.get(file_path, 0)
                with CLEANUP_PROGRESS.get_lock():
                    progress = int(processed_size / total_size * 85) if total_size else 85
                    CLEANUP_PROGRESS.value = min(progress, 85)

        # --- Phase 2: Directory cleanup (85-95%) ---
        all_dirs = set()
        for d in source_dirs:
            disk_root_match = re.match(r"(/mnt/disk\d+)", d)
            if disk_root_match:
                disk_root = disk_root_match.group(1)
                current = d
                while current and current.startswith(disk_root) and current != disk_root:
                    all_dirs.add(current)
                    current = os.path.dirname(current)
        all_dirs_sorted = sorted(all_dirs, key=lambda x: -x.count(os.sep))
        dir_total = len(all_dirs_sorted)
        for i, d in enumerate(all_dirs_sorted):
            try:
                if os.path.isdir(d) and not os.listdir(d):
                    os.rmdir(d)
            except Exception:
                pass  # Ignore errors (e.g., not empty, permission denied)
            # Update progress (85-95%)
            with CLEANUP_PROGRESS.get_lock():
                if dir_total:
                    progress = 85 + int((i + 1) / dir_total * 10)
                else:
                    progress = 95
                CLEANUP_PROGRESS.value = min(progress, 95)

        # --- Phase 3: Writing results (95-99%) ---
        with CLEANUP_PROGRESS.get_lock():
            CLEANUP_PROGRESS.value = 95
        cleanup_csv, cleanup_json = write_cleanup_results(
            action="delete",
            original_csv=csv_file,
            affected=deleted,
            failed=failed,
            attempted=attempted,
            operation_type="delete"
        )
        with CLEANUP_PROGRESS.get_lock():
            CLEANUP_PROGRESS.value = 99

        # --- Phase 4: Load summary and finish (100%) ---
        output_dir = os.path.join(current_app.root_path, "static", "output", "cleanup_results")
        json_path = os.path.join(output_dir, cleanup_json)
        summary = {}
        try:
            with open(json_path, "r") as jf:
                summary = json.load(jf)
        except Exception as e:
            summary = {"error": f"Could not load summary JSON: {e}"}
        message = f"Deleted {len(deleted)} files."
        if failed:
            message += f" {len(failed)} files could not be deleted."
        summary["message"] = message

        with CLEANUP_PROGRESS.get_lock():
            CLEANUP_PROGRESS.value = 100

        return summary, 200
    except Exception as e:
        with CLEANUP_PROGRESS.get_lock():
            CLEANUP_PROGRESS.value = 100
        return {"error": f"Failed to process CSV: {e}"}, 500

def move_duplicates_logic(csv_file, destination):
    if "/" in csv_file or "\\" in csv_file or not csv_file.endswith(".csv"):
        return {"error": "Invalid file name."}, 400

    if not destination or not isinstance(destination, str):
        return {"error": "Destination directory is required."}, 400

    destination = os.path.abspath(destination)
    if not destination.startswith("/mnt/") and not destination.startswith("/tmp/"):
        return {"error": "Destination must be a valid data directory."}, 400

    if not os.path.isdir(destination):
        try:
            os.makedirs(destination, exist_ok=True)
        except Exception as e:
            return {"error": f"Could not create destination directory: {e}"}, 500

    scan_dir = os.path.join(current_app.root_path, "static", "output", "scan_results")
    csv_path = os.path.join(scan_dir, csv_file)

    if not os.path.isfile(csv_path):
        return {"error": "CSV file not found."}, 404

    moved = []
    failed = []
    attempted = []
    source_dirs = set()

    # Read all rows first to get total for progress
    with open(csv_path, newline="") as f:
        reader_list = list(csv.DictReader(f))
    total = sum(1 for row in reader_list if row.get("Keep", "").strip().lower() != "yes" and row.get("Full Path", "").strip())

    # --- Free space check before moving ---
    file_size_map = {}
    total_size = 0
    for row in reader_list:
        keep = row.get("Keep", "").strip().lower()
        file_path = row.get("Full Path", "").strip()
        if keep != "yes" and file_path and os.path.exists(file_path):
            try:
                size = os.path.getsize(file_path)
                file_size_map[file_path] = size
                total_size += size
            except Exception:
                file_size_map[file_path] = 0
    usage = shutil.disk_usage(destination)
    if total_size > usage.free:
        return {
            "error": (
                f"Not enough free space at destination. "
                f"Required: {total_size/1024/1024:.2f} MB, "
                f"Available: {usage.free/1024/1024:.2f} MB"
            )
        }, 400

    try:
        # --- Phase 1: File processing (0–85%) with byte-accurate progress ---
        file_size_map = {}
        total_size = 0

        # First pass: build file size map
        for row in reader_list:
            keep = row.get("Keep", "").strip().lower()
            file_path = row.get("Full Path", "").strip()
            if keep != "yes" and file_path and os.path.exists(file_path):
                try:
                    size = os.path.getsize(file_path)
                    file_size_map[file_path] = size
                    total_size += size
                except Exception:
                    file_size_map[file_path] = 0  # Can't stat, assume 0

        processed_size = 0

        # Second pass: move files and update progress
        for row in reader_list:
            keep = row.get("Keep", "").strip().lower()
            file_path = row.get("Full Path", "").strip()
            if keep != "yes" and file_path:
                with CURRENT_FILE_NAME.get_lock():
                    CURRENT_FILE_NAME.value = file_path.encode("utf-8")[:255]

                match = re.search(r"/mnt/disk\d+/(.+)", file_path)
                if match:
                    rel_path = match.group(1)
                    dest_path = os.path.join(destination, rel_path)
                else:
                    print(f"Could not determine relative path for {file_path}")
                    sys.stdout.flush()
                    failed.append(f"Could not determine relative path for {file_path}")
                    continue

                attempted.append({"from": file_path, "to": dest_path})
                try:
                    if os.path.exists(file_path):
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        print(f"Moving: {file_path} -> {dest_path}")
                        sys.stdout.flush()
                        copy_with_progress(file_path, dest_path)
                        moved.append({"from": file_path, "to": dest_path})
                except Exception as e:
                    print(f"Failed to move {file_path} -> {dest_path}: {e}")
                    sys.stdout.flush()
                    failed.append(f"{file_path}: {e}")

                # Update progress based on size
                processed_size += file_size_map.get(file_path, 0)
                with CLEANUP_PROGRESS.get_lock():
                    progress = int(processed_size / total_size * 85) if total_size else 85
                    CLEANUP_PROGRESS.value = min(progress, 85)         

        with CURRENT_FILE_NAME.get_lock():
            CURRENT_FILE_NAME.value = b""

        # --- Phase 2: Directory cleanup (85-95%) ---
        all_dirs = set()
        for d in source_dirs:
            disk_root_match = re.match(r"(/mnt/disk\d+)", d)
            if disk_root_match:
                disk_root = disk_root_match.group(1)
                current = d
                while current and current.startswith(disk_root) and current != disk_root:
                    all_dirs.add(current)
                    current = os.path.dirname(current)
        all_dirs_sorted = sorted(all_dirs, key=lambda x: -x.count(os.sep))
        dir_total = len(all_dirs_sorted)
        for i, d in enumerate(all_dirs_sorted):
            try:
                if os.path.isdir(d) and not os.listdir(d):
                    os.rmdir(d)
            except Exception:
                pass
            # Update progress (85-95%)
            with CLEANUP_PROGRESS.get_lock():
                if dir_total:
                    progress = 85 + int((i + 1) / dir_total * 10)
                else:
                    progress = 95
                CLEANUP_PROGRESS.value = min(progress, 95)

        # --- Phase 3: Writing results (95-99%) ---
        with CLEANUP_PROGRESS.get_lock():
            CLEANUP_PROGRESS.value = 95
        cleanup_csv, cleanup_json = write_cleanup_results(
            action="move",
            original_csv=csv_file,
            affected=moved,
            failed=failed,
            attempted=attempted,
            operation_type="move"
        )
        with CLEANUP_PROGRESS.get_lock():
            CLEANUP_PROGRESS.value = 99

        # --- Phase 4: Load summary and finish (100%) ---
        output_dir = os.path.join(current_app.root_path, "static", "output", "cleanup_results")
        json_path = os.path.join(output_dir, cleanup_json)
        summary = {}
        try:
            with open(json_path, "r") as jf:
                summary = json.load(jf)
        except Exception as e:
            summary = {"error": f"Could not load summary JSON: {e}"}
        message = f"Moved {len(moved)} files."
        if failed:
            message += f" {len(failed)} files could not be moved."
        summary["message"] = message

        with CLEANUP_PROGRESS.get_lock():
            CLEANUP_PROGRESS.value = 100

        return summary, 200
    except Exception as e:
        with CLEANUP_PROGRESS.get_lock():
            CLEANUP_PROGRESS.value = 100
        return {"error": f"Failed to process CSV: {e}"}, 500
