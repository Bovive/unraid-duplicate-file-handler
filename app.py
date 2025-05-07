# app.py
import sys
from pathlib import Path
from flask import Flask
import logging  # Import the logging module

# Ensure the root directory is in sys.path for module imports
sys.path.append(str(Path(__file__).resolve().parent))

from modules.routes import routes  # Import the Blueprint
from config import SECRET_KEY  # Import the secret key

app = Flask(__name__)

# Suppress Flask's request logs by setting the werkzeug logger level to ERROR
log = logging.getLogger('werkzeug')
log.setLevel(logging.DEBUG)

# Set the secret key for CSRF protection
app.secret_key = SECRET_KEY

# Register the Blueprint
app.register_blueprint(routes)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

