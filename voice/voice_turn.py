import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


RECORD_SECONDS = int(os.environ.get("VAL_RECORD_SECONDS", "5"))
AUDIO_DEVICE = os.environ.get("VAL_AUDIO_DEVICE", "plughw:0,0")
WHISPER_URL = os.environ.get("VAL_WHISPER_URL", "http://val-whisper:8080/inference")
CONTROLLER_URL = os.environ.get("VAL_CONTROLLER_URL", "http://val-controller:8092/chat")
PIPER_URL = os.environ.get("VAL_PIPER_URL", "http://val-piper:5000/")

REQUEST_AUDIO = Path("/tmp/val-request.wav")
RESPONSE_AUDIO = Path("/tmp/val-response.wav")


def record_request():
    print(f"Recording for {RECORD_SECONDS} seconds. Speak now...", flush=True)
    subprocess.run(
        [
            "arecord",
            "-q",
            "-D",
            AUDIO_DEVICE,
            "-d",
            str(RECORD_SECONDS),
            "-f",
            "S16_LE",
            "-r",
            "16000",
            "-c",
            "1",
            str(REQUEST_AUDIO),
        ],
        check=True,
    )


def transcribe_request():
    result = subprocess.run(
        [
            "curl",
            "-fsS",
            "--url",
            WHISPER_URL,
            "-F",
            f"file=@{REQUEST_AUDIO}",
            "-F",
            "response_format=json",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    transcription = json.loads(result.stdout)["text"].strip()
    if not transcription:
        raise RuntimeError("Whisper returned an empty transcription")
    print(f"You: {transcription}", flush=True)
    return transcription


def post_json(url, payload, timeout):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def ask_val(transcription):
    response = json.loads(
        post_json(CONTROLLER_URL, {"message": transcription}, timeout=120)
    )
    answer = response["response"].strip()
    if not answer:
        raise RuntimeError("Val returned an empty response")
    print(f"Val: {answer}", flush=True)
    return answer


def speak_answer(answer):
    RESPONSE_AUDIO.write_bytes(post_json(PIPER_URL, {"text": answer}, timeout=60))
    subprocess.run(
        ["aplay", "-q", "-D", AUDIO_DEVICE, str(RESPONSE_AUDIO)],
        check=True,
    )


def main():
    record_request()
    transcription = transcribe_request()
    answer = ask_val(transcription)
    speak_answer(answer)
    print("Voice turn complete.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (subprocess.SubprocessError, urllib.error.URLError, OSError, ValueError) as error:
        print(f"Voice turn failed: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
