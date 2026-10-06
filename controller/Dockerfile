FROM python:3.13-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends alsa-utils tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY val_controller.py /app/val_controller.py
COPY tooling.py /app/tooling.py
COPY server_status.py /app/server_status.py
COPY discovery.py /app/discovery.py

RUN useradd --create-home --uid 10001 val

USER val

EXPOSE 8092

CMD ["python", "/app/val_controller.py"]
