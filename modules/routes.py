from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, jsonify
from modules.scan import scan_for_duplicates, get_array_drives, get_pool_drives, SCAN_PROGRESS, is_canceled
from modules.forms import ScanForm
from config import APP_NAME, APP_VERSION
from threading import Thread, Event, Lock

# Create a Blueprint for routes
routes = Blueprint("routes", __name__)

# Global variables
scan_summary_data = None
scan_complete_event = Event()
scan_summary_lock = Lock()
is_scanning = False  # Flag to track if a scan is in progress
is_scanning_lock = Lock()  # Lock for thread-safe access to is_scanning
is_canceled = False

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
@routes.route("/start_scan", methods=["POST"])
def start_scan():
    global scan_summary_data, is_scanning
    with is_scanning_lock:
        if is_scanning:
            print("DEBUG: Scan already in progress.")
            return jsonify({"error": "A scan is already in progress. Please wait for it to complete."}), 400

        is_scanning = True  # Set the flag to indicate a scan is in progress
        print("DEBUG: Scan started. is_scanning set to True.")

    form = ScanForm(request.form)

    # Dynamically populate the drives choices
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
        ext_filter = [ext.strip() for ext in form.ext_filter.data.split(",") if ext.strip()]
        keep_strategy = form.keep_strategy.data

        app = current_app._get_current_object()

        # Reset scan state
        scan_complete_event.clear()  # Clear the event before starting a new scan
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
                    print("DEBUG: Scan completed successfully.")
                else:
                    print("DEBUG: Scan was canceled. Summary not set.")
                    scan_complete_event.set()  # 🔥 So the frontend knows it’s over
            except Exception as e:
                print(f"DEBUG: Exception during scan: {e}")
            finally:
                with is_scanning_lock:
                    is_scanning = False  # Ensure the flag is reset even if an exception occurs
                    print("DEBUG: is_scanning reset to False.")

        thread = Thread(target=run_scan, daemon=True)
        thread.start()
        return "", 200
    else:
        with is_scanning_lock:
            is_scanning = False  # Reset the flag if form validation fails
            print("DEBUG: Form validation failed. is_scanning reset to False.")
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
