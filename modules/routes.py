from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, jsonify
from modules.scan import scan_for_duplicates, get_array_drives, get_pool_drives, SCAN_PROGRESS
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

@routes.route("/")
def index():
    return render_template("index.html", app_name=APP_NAME, app_version=APP_VERSION)

@routes.route("/scan", methods=["GET", "POST"])
def scan():
    global scan_summary_data, is_scanning
    form = ScanForm()
    scan_results = None
    scanning = is_scanning  # Pass the scanning state to the template

    # Determine the source choice (default to "1" if not set)
    source_choice = form.source_choice.data or "1"

    # Dynamically populate the drives choices
    available_drives = {
        "1": get_array_drives(),
        "2": get_pool_drives(),
        "3": get_array_drives() + get_pool_drives(),
    }
    form.drives.choices = [(d, d) for d in available_drives.get(source_choice, [])]

    if form.validate_on_submit():
        if is_scanning:
            flash("A scan is already in progress. Please wait for it to complete.", "warning")
        else:
            try:
                selected_drives = form.drives.data
                min_size = int(form.min_size.data or 0)
                ext_filter = [e.strip() for e in form.ext_filter.data.split(",")] if form.ext_filter.data else []
                keep_strategy = form.keep_strategy.data

                app = current_app._get_current_object()

                def run_scan():
                    global scan_summary_data, is_scanning
                    with is_scanning_lock:
                        is_scanning = True
                    print("Starting scan...")
                    try:
                        with scan_summary_lock:
                            scan_summary_data = scan_for_duplicates(
                                selected_drives,
                                min_size=min_size,
                                ext_filter=ext_filter,
                                keep_strategy=keep_strategy,
                                app=app,
                            )
                        scan_complete_event.set()  # Signal that the scan is complete
                        print("Scan completed. Summary:", scan_summary_data)
                    finally:
                        with is_scanning_lock:
                            is_scanning = False  # Ensure the flag is reset even if an exception occurs

                thread = Thread(target=run_scan)
                thread.start()

                flash("Scan started successfully!", "info")
                scanning = True
            except Exception as e:
                flash(f"An error occurred during the scan: {e}", "danger")

    return render_template(
        "scan.html",
        form=form,
        scan_results=scan_results,
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
def start_scan():
    global scan_summary_data, is_scanning
    with is_scanning_lock:
        if is_scanning:
            return jsonify({"error": "A scan is already in progress. Please wait for it to complete."}), 400

        is_scanning = True  # Set the flag to indicate a scan is in progress

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
        scan_complete_event.clear()
        with scan_summary_lock:
            scan_summary_data = None
        with SCAN_PROGRESS.get_lock():
            SCAN_PROGRESS.value = 0

        def run_scan():
            global scan_summary_data, is_scanning
            try:
                with scan_summary_lock:
                    scan_summary_data = scan_for_duplicates(
                        selected_disks, min_size, ext_filter, keep_strategy, app
                    )
                scan_complete_event.set()
            finally:
                with is_scanning_lock:
                    is_scanning = False  # Ensure the flag is reset even if an exception occurs

        thread = Thread(target=run_scan, daemon=True)
        thread.start()
        return "", 200
    else:
        with is_scanning_lock:
            is_scanning = False  # Reset the flag if form validation fails
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
