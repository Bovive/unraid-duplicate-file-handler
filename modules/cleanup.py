import os, csv, json, shutil
from datetime import datetime
from flask import current_app
from multiprocessing import Value

# Global progress variable for cleanup actions
CLEANUP_PROGRESS = Value("i", 0)

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
        reader = list(csv.DictReader(f))
    total = sum(1 for row in reader if row.get("Keep", "").strip().lower() != "yes" and row.get("Full Path", "").strip())

    try:
        # --- Phase 1: File processing (0-85%) ---
        for idx, row in enumerate(reader):
            keep = row.get("Keep", "").strip().lower()
            file_path = row.get("Full Path", "").strip()
            if keep != "yes" and file_path:
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
            # Update progress (0-85%)
            with CLEANUP_PROGRESS.get_lock():
                progress = int((idx + 1) / total * 85) if total else 85
                CLEANUP_PROGRESS.value = min(progress, 85)

        # --- Phase 2: Directory cleanup (85-95%) ---
        all_dirs = set()
        for d in source_dirs:
            while True:
                if d == scan_root.rstrip(os.sep) or not d.startswith(scan_root):
                    break
                all_dirs.add(d)
                d = os.path.dirname(d)
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

    scan_root = "/mnt/disk6/storage/"

    moved = []
    failed = []
    attempted = []
    source_dirs = set()

    # Read all rows first to get total for progress
    with open(csv_path, newline="") as f:
        reader = list(csv.DictReader(f))
    total = sum(1 for row in reader if row.get("Keep", "").strip().lower() != "yes" and row.get("Full Path", "").strip())

    try:
        # --- Phase 1: File processing (0-85%) ---
        for idx, row in enumerate(reader):
            keep = row.get("Keep", "").strip().lower()
            file_path = row.get("Full Path", "").strip()
            if keep != "yes" and file_path:
                rel_path = os.path.relpath(file_path, scan_root)
                dest_path = os.path.join(destination, rel_path)
                attempted.append({"from": file_path, "to": dest_path})
                try:
                    if os.path.exists(file_path):
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.move(file_path, dest_path)
                        moved.append({"from": file_path, "to": dest_path})
                        source_dirs.add(os.path.dirname(file_path))
                    else:
                        failed.append(f"File not found: {file_path}")
                except Exception as e:
                    failed.append(f"{file_path}: {e}")
            # Update progress (0-85%)
            with CLEANUP_PROGRESS.get_lock():
                progress = int((idx + 1) / total * 85) if total else 85
                CLEANUP_PROGRESS.value = min(progress, 85)

        # --- Phase 2: Directory cleanup (85-95%) ---
        all_dirs = set()
        for d in source_dirs:
            while True:
                if d == scan_root.rstrip(os.sep) or not d.startswith(scan_root):
                    break
                all_dirs.add(d)
                d = os.path.dirname(d)
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

