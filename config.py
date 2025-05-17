# config.py
import os

APP_NAME = "Unraid Duplicate File Handler"
APP_VERSION = "1.0.1"

# Secret key for CSRF protection
SECRET_KEY = os.getenv("SECRET_KEY", "default_development_secret_key")
