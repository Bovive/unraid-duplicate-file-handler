# routes.py
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from modules.scan import scan_for_duplicates, get_array_drives, get_pool_drives, SCAN_PROGRESS
from modules.forms import ScanForm
from config import APP_NAME, APP_VERSION
from threading import Thread

# Create a Blueprint for routes
routes = Blueprint("routes", __name__)

@routes.route("/")
def index():
    return render_template("index.html", app_name=APP_NAME, app_version=APP_VERSION)

@routes.route("/scan", methods=["GET", "POST"])
def scan():
    form = ScanForm()
    scan_results = None
    scanning = False

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
        try:
            selected_drives = form.drives.data
            min_size = int(form.min_size.data or 0)
            ext_filter = [e.strip() for e in form.ext_filter.data.split(",")] if form.ext_filter.data else []
            keep_strategy = form.keep_strategy.data

            app = current_app._get_current_object()
            thread = Thread(target=scan_for_duplicates, args=(selected_drives,), kwargs={
                "min_size": min_size,
                "ext_filter": ext_filter,
                "keep_strategy": keep_strategy,
                "app": app
            })
            thread.start()

            flash("Scan started successfully!", "info")
            scanning = True
        except Exception as e:
            flash(f"An error occurred during the scan: {e}", "danger")

    return render_template("scan.html", form=form, scan_results=scan_results, scanning=scanning)

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
    print(f"Progress route called. Current progress: {progress}%")  # Add logging
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
    form = ScanForm(request.form)

    # Dynamically populate the drives choices
    source_choice = form.source_choice.data or "1"
    available_drives = {
        "1": get_array_drives(),
        "2": get_pool_drives(),
        "3": get_array_drives() + get_pool_drives(),
    }
    form.drives.choices = [(d, d) for d in available_drives.get(source_choice, [])]

    print("Submitted drives:", request.form.getlist("drives"))  # Log submitted drives
    print("Form choices:", form.drives.choices)  # Log form choices

    if form.validate():
        selected_disks = form.drives.data
        min_size = int(form.min_size.data or 0)
        ext_filter = [ext.strip() for ext in form.ext_filter.data.split(",") if ext.strip()]
        keep_strategy = form.keep_strategy.data

        thread = Thread(
            target=scan_for_duplicates,
            args=(selected_disks, min_size, ext_filter, keep_strategy, current_app._get_current_object()),
            daemon=True
        )
        thread.start()
        return "", 200
    else:
        print("Form validation failed:", form.errors)
        return "Invalid form submission", 400


