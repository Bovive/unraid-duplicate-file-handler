from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, jsonify, send_from_directory
from modules.scan import scan_for_duplicates, get_array_drives, get_pool_drives, SCAN_PROGRESS, is_canceled
from modules.cleanup import write_cleanup_results, delete_duplicates_logic, move_duplicates_logic, CLEANUP_PROGRESS
from modules.forms import ScanForm
from config import APP_NAME, APP_VERSION
from threading import Thread, Event, Lock
from werkzeug.datastructures import MultiDict
import os, glob, json, csv, shutil

# Create a Blueprint for routes
routes = Blueprint("routes", __name__)

# Global variables
scan_summary_data = None
scan_complete_event = Event()
scan_summary_lock = Lock()
is_scanning = False  # Flag to track if a scan is in progress
is_scanning_lock = Lock()  # Lock for thread-safe access to is_scanning
is_canceled = False
cleanup_results = {}
cleanup_threads = {}

@routes.route("/")
def index():
    return render_template("index.html", app_name=APP_NAME, app_version=APP_VERSION)

@routes.route("/scan", methods=["GET"])
def scan():
    global is_scanning
    form = ScanForm()
    scanning = is_scanning

    # Determine source choice from request args or fallback to "1"
    source_choice = request.args.get("source_choice") or "1"

    # Dynamically populate the drives
    available_drives = {
        "1": get_array_drives(),
        "2": get_pool_drives(),
        "3": get_array_drives() + get_pool_drives(),
    }
    form.drives.choices = [(d, d) for d in available_drives.get(source_choice, [])]

    return render_template(
        "scan.html",
        form=form,
        scan_results=None,
        scanning=scanning,
    )

@routes.route("/cleanup", methods=["GET", "POST"])
def cleanup():
    if request.method == "POST":
        try:
            cleanup_duplicates()
            flash("Cleanup completed successfully!", "success")
        except Exception as e:
            flash(f"An error occurred during cleanup: {e}", "danger")
        return redirect(url_for("routes.cleanup"))
    return render_template("cleanup.html")  # Render the cleanup form for GET requests

@routes.route("/progress", methods=["GET"])
def progress():
    with SCAN_PROGRESS.get_lock():
        progress = SCAN_PROGRESS.value
    return {"progress": progress}

@routes.route("/cleanup_progress", methods=["GET"])
def cleanup_progress():
    with CLEANUP_PROGRESS.get_lock():
        progress = CLEANUP_PROGRESS.value
    return {"progress": progress}

@routes.route("/get_drives/<source_choice>", methods=["GET"])
def get_drives(source_choice):
    """Return the list of drives based on the source choice."""
    available_drives = {
        "1": get_array_drives(),  # Array drives excluding parity
        "2": get_pool_drives(),   # Pool drives
        "3": get_array_drives() + get_pool_drives(),  # Both
    }
    return {"drives": available_drives.get(source_choice, [])}

@routes.route("/start_scan", methods=["POST"])
def start_scan():
    global scan_summary_data, is_scanning

    with is_scanning_lock:
        if is_scanning:
            return jsonify({"error": "A scan is already in progress. Please wait for it to complete."}), 400
        is_scanning = True

    form = ScanForm(request.form)

    # Dynamically populate the drives choices based on source_choice
    source_choice = form.source_choice.data or "1"
    available_drives = {
        "1": get_array_drives(),
        "2": get_pool_drives(),
        "3": get_array_drives() + get_pool_drives(),
    }
    form.drives.choices = [(d, d) for d in available_drives.get(source_choice, [])]

    if form.validate():
        selected_disks = form.drives.data
        min_size = int(form.min_size.data or 0)
        ext_filter = [ext.strip() for ext in (form.ext_filter.data or "").split(",") if ext.strip()]
        keep_strategy = [
            form.keep_primary.data,
            form.keep_tiebreaker1.data,
            form.keep_tiebreaker2.data,
        ]
        keep_strategy = [s for s in keep_strategy if s]  # Remove blanks

        app = current_app._get_current_object()

        # Reset scan state
        scan_complete_event.clear()
        with scan_summary_lock:
            scan_summary_data = None
        with SCAN_PROGRESS.get_lock():
            SCAN_PROGRESS.value = 0

        def run_scan():
            global scan_summary_data, is_scanning
            try:
                result = scan_for_duplicates(
                    selected_disks, min_size, ext_filter, keep_strategy, app
                )
                if result is not None:
                    with scan_summary_lock:
                        scan_summary_data = result
                    scan_complete_event.set()
                else:
                    scan_complete_event.set()
            except Exception as e:
                print(f"Exception during scan: {e}")
            finally:
                with is_scanning_lock:
                    is_scanning = False

        thread = Thread(target=run_scan, daemon=True)
        thread.start()
        return "", 200
    else:
        with is_scanning_lock:
            is_scanning = False
        return jsonify({"error": "Invalid form submission", "details": form.errors}), 400

@routes.route("/scan-summary", methods=["GET"])
def scan_summary():
    """Return the scan summary."""
    global scan_summary_data  # Ensure this is accessible
    if not scan_complete_event.is_set():
        print("Scan summary requested but scan is still in progress.")
        return jsonify({"error": "Scan is still in progress."}), 202  # Return 202 Accepted if scan is not complete
    print("Scan summary content:", scan_summary_data)
    try:
        with scan_summary_lock:
            return jsonify(scan_summary_data)
    except TypeError as e:
        print("Error serializing scan_summary_data:", e)
        return jsonify({"error": "Scan summary contains non-serializable data.", "details": str(scan_summary_data)}), 500

@routes.route("/cancel_scan", methods=["POST"])
def cancel_scan():
    from modules import scan
    scan.is_canceled = True
    print("DEBUG: is_canceled set to True from /cancel_scan")
    return jsonify({"message": "Scan canceled successfully."}), 200

@routes.route("/download_csv/<filename>")
def download_csv(filename):
    # Try cleanup_results first
    cleanup_dir = os.path.join(current_app.root_path, "static", "output", "cleanup_results")
    scan_dir = os.path.join(current_app.root_path, "static", "output", "scan_results")
    # Security: prevent path traversal
    if "/" in filename or "\\" in filename:
        return "Invalid filename", 400
    # Check cleanup_results
    cleanup_path = os.path.join(cleanup_dir, filename)
    if os.path.isfile(cleanup_path):
        return send_from_directory(cleanup_dir, filename, as_attachment=True)
    # Check scan_results
    scan_path = os.path.join(scan_dir, filename)
    if os.path.isfile(scan_path):
        return send_from_directory(scan_dir, filename, as_attachment=True)
    # Not found
    return "File not found", 404

@routes.route("/list_scan_summaries")
def list_scan_summaries():
    output_dir = os.path.join(current_app.root_path, "static", "output", "scan_results")
    summaries = []
    for json_path in sorted(glob.glob(os.path.join(output_dir, "duplicates_*.json")), reverse=True):
        try:
            with open(json_path, "r") as f:
                summary = json.load(f)
                # Only include if there are duplicates and a CSV file
                if summary.get("csv_file") and summary.get("total_duplicates") and summary.get("total_duplicates") != "0":
                    summaries.append(summary)
        except Exception as e:
            print(f"Error reading summary {json_path}: {e}")
    return jsonify({"summaries": summaries})

@routes.route("/delete_duplicates/<csv_file>", methods=["POST"])
def delete_duplicates(csv_file):
    app = current_app._get_current_object()
    def run_cleanup():
        with app.app_context():
            result, status = delete_duplicates_logic(csv_file)
            cleanup_results[csv_file] = (result, status)
    with CLEANUP_PROGRESS.get_lock():
        CLEANUP_PROGRESS.value = 0
    thread = Thread(target=run_cleanup, daemon=True)
    cleanup_threads[csv_file] = thread
    thread.start()
    return jsonify({"started": True}), 202

@routes.route("/cleanup_result/<csv_file>")
def cleanup_result(csv_file):
    result = cleanup_results.get(csv_file)
    if result:
        return jsonify(result[0]), result[1]
    return jsonify({"status": "running"}), 202

@routes.route("/move_duplicates/<csv_file>", methods=["POST"])
def move_duplicates(csv_file):
    data = request.get_json()
    destination = data.get("destination") if data else None
    app = current_app._get_current_object()  # Capture the app object

    def run_move():
        with app.app_context():  # Use the captured app object
            result, status = move_duplicates_logic(csv_file, destination)
            cleanup_results[csv_file] = (result, status)
    with CLEANUP_PROGRESS.get_lock():
        CLEANUP_PROGRESS.value = 0
    thread = Thread(target=run_move, daemon=True)
    cleanup_threads[csv_file] = thread
    thread.start()
    return jsonify({"started": True}), 202

@routes.route("/list_dirs", methods=["POST"])
def list_dirs():
    data = request.get_json()
    base = data.get("base", "/mnt")
    # Security: Only allow navigation under /mnt
    base = os.path.abspath(base)
    if not base.startswith("/mnt"):
        return jsonify({"error": "Invalid base directory."}), 400
    try:
        dirs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
        dirs.sort()
        return jsonify({"dirs": dirs, "base": base})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@routes.route("/cleanup_history")
def cleanup_history():
    return render_template("cleanup_history.html")

@routes.route("/list_cleanup_history")
def list_cleanup_history():
    # Adjust the path to where your cleanup job summaries are stored
    output_dir = os.path.join(current_app.root_path, "static", "output", "cleanup_results")
    history = []
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    for json_path in sorted(glob.glob(os.path.join(output_dir, "cleanup_*.json")), reverse=True):
        try:
            with open(json_path, "r") as f:
                summary = json.load(f)
                history.append(summary)
        except Exception as e:
            print(f"Error reading cleanup history {json_path}: {e}")
    return jsonify({"history": history})
