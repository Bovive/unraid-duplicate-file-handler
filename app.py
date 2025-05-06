# app.py
from flask import Flask, render_template, request, redirect, url_for
from modules.scan import scan_for_duplicates
from modules.cleanup import cleanup_duplicates

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scan", methods=["POST"])
def scan():
    scan_for_duplicates()
    return redirect(url_for("index"))

@app.route("/cleanup", methods=["POST"])
def cleanup():
    cleanup_duplicates()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
