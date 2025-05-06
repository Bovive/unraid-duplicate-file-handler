FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY unraid_dupe_handler.py /app/
COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

# Override /bin/sh to point to our script via a wrapper
RUN echo '#!/bin/sh\nexec python /app/unraid_dupe_handler.py' > /bin/custom_shell && chmod +x /bin/custom_shell && ln -sf /bin/custom_shell /bin/sh
