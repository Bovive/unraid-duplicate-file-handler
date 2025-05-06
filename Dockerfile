FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY unraid_dupe_handler.py /app/
COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

# Run script automatically when bash shell is opened
RUN echo 'python /app/unraid_dupe_handler.py' >> /root/.bashrc

CMD ["python", "unraid_dupe_handler.py"]
