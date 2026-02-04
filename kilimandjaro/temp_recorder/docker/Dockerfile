FROM python:slim
RUN apt update && apt install -y bluez && rm -rf /var/lib/apt/lists/*
RUN pip install bleak datadog
COPY listen.py /app/listen.py
COPY entrypoint.sh /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
