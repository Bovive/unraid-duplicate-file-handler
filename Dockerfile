# Use a lightweight Python image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy source code into container
COPY app.py requirements.txt config.py /app/
COPY templates/ /app/templates/
COPY modules/ /app/modules/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variable for the secret key
ENV SECRET_KEY="your_production_secret_key"

# Expose Flask default port
EXPOSE 5000

# Run the Flask app
CMD ["python", "app.py"]

