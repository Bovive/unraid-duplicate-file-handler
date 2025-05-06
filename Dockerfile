FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY unraid_dupe_handler.py /app/
COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

# Create a wrapper that always runs the script when the container shell is opened
RUN echo '#!/bin/sh\npython /app/unraid_dupe_handler.py' > /usr/local/bin/dupe_entrypoint && chmod +x /usr/local/bin/dupe_entrypoint

# Set that wrapper as the default shell
CMD ["/usr/local/bin/dupe_entrypoint"]
