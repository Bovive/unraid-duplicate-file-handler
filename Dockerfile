FROM python:3.9-slim

# Disable Python output buffering
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY unraid_dupe_handler.py /app/
COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "unraid_dupe_handler.py"]
