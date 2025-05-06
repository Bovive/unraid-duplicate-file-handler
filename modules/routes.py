# routes.py
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from modules.scan import scan_for_duplicates, get_array_drives, get_pool_drives
from modules.forms import ScanForm
from config import APP_NAME, APP_VERSION

# Create a Blueprint for routes
routes = Blueprint("routes", __name__)

@routes.route("/")
def index():
    return render_template("index.html", app_name=APP_NAME, app_version=APP_VERSION)

@routes.route("/scan", methods=["GET", "POST"])
def scan():
    form = ScanForm()
    scan_results = None  # To store scan metrics

    # Dynamically populate drives based on the source choice
    available_drives = {
        "1": get_array_drives(),  # Array drives excluding parity
        "2": get_pool_drives(),   # Pool drives
        "3": get_array_drives() + get_pool_drives(),  # Both
    }
    if form.source_choice.data:
        form.drives.choices = [(drive, drive) for drive in available_drives.get(form.source_choice.data, [])]

    if form.validate_on_submit():
        try:
            selected_drives = form.drives.data
            # Pass selected drives to the scan logic and get scan metrics
            scan_results = scan_for_duplicates(selected_drives)
            flash("Scan completed successfully!", "success")
        except Exception as e:
            flash(f"An error occurred during the scan: {e}", "danger")
        return redirect(url_for("routes.scan"))
    
    return render_template("scan.html", form=form, scan_results=scan_results)

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
    progress = current_app.config.get("SCAN_PROGRESS", 0)
    return {"progress": progress}

