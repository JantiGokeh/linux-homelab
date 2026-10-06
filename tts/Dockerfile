FROM python:3.12-slim

RUN pip install --no-cache-dir 'piper-tts[http]==1.4.2'

WORKDIR /work

ENTRYPOINT ["python", "-m", "piper"]
