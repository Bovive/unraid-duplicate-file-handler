# Use a lightweight Python base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the script and configuration file into the container
COPY unraid_dupe_handler.py /app/
COPY dupe_config.conf /app/  # Optional: If you want to include a default config

# Install any required Python libraries (if needed)
# Add dependencies here if the script uses external libraries
RUN pip install --no-cache-dir -r requirements.txt || true

# Set the default command to run the script
CMD ["python", "unraid_dupe_handler.py"]
