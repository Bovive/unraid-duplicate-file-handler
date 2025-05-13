import os
import csv
import shutil
import json
from datetime import datetime
from flask import current_app

def write_cleanup_results(action, original_csv, affected, failed, operation_type):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base_name = os.path.splitext(os.path.basename(original_csv))[0]
    output_dir = os.path.join(current_app.root_path, "static", "output", "scan_results")
    csv_filename = f"cleanup_{base_name}_{operation_type}_{timestamp}.csv"
    json_filename = f"cleanup_{base_name}_{operation_type}_{timestamp}.json"
    csv_path = os.path.join(output_dir, csv_filename)
    json_path = os.path.join(output_dir, json_filename)

    # Write CSV
    with open(csv_path, "w", newline="") as f:
        if operation_type == "delete":
            writer = csv.writer(f)
            writer.writerow(["File Path"])
            for file_path in affected:
                writer.writerow([file_path])
        elif operation_type == "move":
            writer = csv.writer(f)
            writer.writerow(["From", "To"])
            for move_info in affected:
                writer.writerow([move_info["from"], move_info["to"]])

    # Write JSON summary
    summary = {
        "action": action,
        "timestamp": timestamp,
        "original_csv": original_csv,
        "csv_file": csv_filename,
        "total_affected": len(affected),
        "total_failed": len(failed),
        "affected": affected,
        "failed": failed,
    }
    with open(json_path, "w") as jf:
        json.dump(summary, jf, indent=2)
    return csv_filename, json_filename

def delete_duplicates_logic(csv_file):
    if "/" in csv_file or "\\" in csv_file or not csv_file.endswith(".csv"):
        return {"error": "Invalid file name."}, 400

    output_dir = os.path.join(current_app.root_path, "static", "output", "scan_results")
    csv_path = os.path.join(output_dir, csv_file)

    if not os.path.isfile(csv_path):
        return {"error": "CSV file not found."}, 404

    deleted = []
    failed = []

    try:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                keep = row.get("Keep", "").strip().lower()
                file_path = row.get("Full Path", "").strip()
                if keep != "yes" and file_path:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            deleted.append(file_path)
                        else:
                            failed.append(f"File not found: {file_path}")
                    except Exception as e:
                        failed.append(f"{file_path}: {e}")
    except Exception as e:
        return {"error": f"Failed to process CSV: {e}"}, 500

    message = f"Deleted {len(deleted)} files."
    if failed:
        message += f" {len(failed)} files could not be deleted."

    cleanup_csv, cleanup_json = write_cleanup_results(
        action="delete",
        original_csv=csv_file,
        affected=deleted,
        failed=failed,
        operation_type="delete"
    )

    return {
        "message": message,
        "deleted": deleted,
        "failed": failed,
        "cleanup_csv": cleanup_csv,
        "cleanup_json": cleanup_json
    }, 200

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

    output_dir = os.path.join(current_app.root_path, "static", "output", "scan_results")
    csv_path = os.path.join(output_dir, csv_file)

    if not os.path.isfile(csv_path):
        return {"error": "CSV file not found."}, 404

    moved = []
    failed = []

    try:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                keep = row.get("Keep", "").strip().lower()
                file_path = row.get("Full Path", "").strip()
                if keep != "yes" and file_path:
                    try:
                        if os.path.exists(file_path):
                            dest_path = os.path.join(destination, os.path.basename(file_path))
                            shutil.move(file_path, dest_path)
                            moved.append({"from": file_path, "to": dest_path})
                        else:
                            failed.append(f"File not found: {file_path}")
                    except Exception as e:
                        failed.append(f"{file_path}: {e}")
    except Exception as e:
        return {"error": f"Failed to process CSV: {e}"}, 500

    message = f"Moved {len(moved)} files."
    if failed:
        message += f" {len(failed)} files could not be moved."

    cleanup_csv, cleanup_json = write_cleanup_results(
        action="move",
        original_csv=csv_file,
        affected=moved,
        failed=failed,
        operation_type="move"
    )

    return {
        "message": message,
        "moved": moved,
        "failed": failed,
        "cleanup_csv": cleanup_csv,
        "cleanup_json": cleanup_json
    }, 200
