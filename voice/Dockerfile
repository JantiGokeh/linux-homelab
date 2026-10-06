FROM python:3.13-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends alsa-utils curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    click==8.2.1 \
    numpy==2.3.3 \
    sentencepiece==0.2.1 \
    sherpa-onnx==1.13.8

WORKDIR /app

COPY voice_turn.py /app/voice_turn.py
COPY wake_test.py /app/wake_test.py
COPY val_voice.py /app/val_voice.py
COPY speech.py /app/speech.py

CMD ["python", "/app/voice_turn.py"]
