# app.py
import sys
from pathlib import Path
from flask import Flask

# Ensure the root directory is in sys.path for module imports
sys.path.append(str(Path(__file__).resolve().parent))

from modules.routes import routes  # Import the Blueprint

app = Flask(__name__)

# Register the Blueprint
app.register_blueprint(routes)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
