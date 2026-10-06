import json
import math
import os
import re
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx

from speech import sanitize_for_speech


SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
CHANNELS = 1
CHUNK_MS = 100
CHUNK_BYTES = SAMPLE_RATE * SAMPLE_WIDTH * CHUNK_MS // 1000

CAPTURE_DEVICE = os.environ.get(
    "VAL_CAPTURE_DEVICE", os.environ.get("VAL_AUDIO_DEVICE", "plughw:0,0")
)
PLAYBACK_DEVICE = os.environ.get(
    "VAL_PLAYBACK_DEVICE", os.environ.get("VAL_AUDIO_DEVICE", "plughw:0,0")
)
MODEL_DIR = os.environ.get(
    "VAL_WAKE_MODEL_DIR",
    "/models/wake/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01",
)
WHISPER_URL = os.environ.get("VAL_WHISPER_URL", "http://val-whisper:8080/inference")
CONTROLLER_URL = os.environ.get("VAL_CONTROLLER_URL", "http://val-controller:8092/chat")
VOICE_STATE_URL = os.environ.get("VAL_VOICE_STATE_URL", "http://val-controller:8092/voice-state")
EVENTS_URL = os.environ.get("VAL_EVENTS_URL", "http://val-controller:8092/events")
PIPER_URL = os.environ.get("VAL_PIPER_URL", "http://val-piper:5000/")

VAD_MODEL = os.environ.get("VAL_VAD_MODEL", "/models/vad/silero_vad.onnx")
VAD_THRESHOLD = float(os.environ.get("VAL_VAD_THRESHOLD", "0.50"))
SLEEP_VAD_THRESHOLD = float(os.environ.get("VAL_SLEEP_VAD_THRESHOLD", "0.25"))
END_SILENCE_SECONDS = float(os.environ.get("VAL_END_SILENCE_SECONDS", "0.8"))
MIN_SPEECH_SECONDS = float(os.environ.get("VAL_MIN_SPEECH_SECONDS", "0.35"))
MAX_SPEECH_SECONDS = float(os.environ.get("VAL_MAX_SPEECH_SECONDS", "20"))
INPUT_GAIN = float(os.environ.get("VAL_INPUT_GAIN", "12.0"))
WAKE_SCORE = float(os.environ.get("VAL_WAKE_SCORE", "6.0"))
WAKE_THRESHOLD = float(os.environ.get("VAL_WAKE_THRESHOLD", "0.05"))

REQUEST_AUDIO = Path("/tmp/val-request.wav")
RESPONSE_AUDIO = Path("/tmp/val-response.wav")
THINKING_AUDIO = Path("/tmp/val-thinking.wav")
RUNNING = True
CURRENT_VOICE_STATE = "sleeping"


def handle_stop(_signum, _frame):
    global RUNNING
    RUNNING = False


def configure_microphone():
    if "CARD=Sound" in CAPTURE_DEVICE:
        subprocess.run(
            ["amixer", "-q", "-c", "1", "sset", "Headset", "cap"], check=True
        )
        print(
            f"Microphone configured: HyperX capture enabled, software gain {INPUT_GAIN:g}x.",
            flush=True,
        )
    else:
        capture_percent = os.environ.get("VAL_CAPTURE_PERCENT", "65")
        subprocess.run(
            ["amixer", "-q", "-c", "0", "sset", "Capture", f"{capture_percent}%", "cap"],
            check=True,
        )
        subprocess.run(
            ["amixer", "-q", "-c", "0", "sset", "Internal Mic Boost", "0"],
            check=True,
        )
        print(f"Microphone configured: capture {capture_percent}%, boost off.", flush=True)


def start_recorder():
    return subprocess.Popen(
        [
            "arecord", "-q", "-D", CAPTURE_DEVICE, "-t", "raw", "-f", "S16_LE",
            "-r", str(SAMPLE_RATE), "-c", str(CHANNELS),
        ],
        stdout=subprocess.PIPE,
    )


def stop_recorder(recorder):
    if recorder.poll() is None:
        recorder.terminate()
        try:
            recorder.wait(timeout=3)
        except subprocess.TimeoutExpired:
            recorder.kill()
            recorder.wait(timeout=3)


def read_chunk(recorder):
    chunk = recorder.stdout.read(CHUNK_BYTES)
    if len(chunk) != CHUNK_BYTES:
        raise RuntimeError("Microphone stream ended unexpectedly")
    return chunk


def samples_from_chunk(chunk):
    samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
    return np.clip(samples * INPUT_GAIN, -1.0, 1.0)


def create_spotter():
    return sherpa_onnx.KeywordSpotter(
        tokens=f"{MODEL_DIR}/tokens.txt",
        encoder=f"{MODEL_DIR}/encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
        decoder=f"{MODEL_DIR}/decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
        joiner=f"{MODEL_DIR}/joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
        num_threads=1,
        max_active_paths=4,
        keywords_file=f"{MODEL_DIR}/hey-val.txt",
        keywords_score=WAKE_SCORE,
        keywords_threshold=WAKE_THRESHOLD,
        num_trailing_blanks=1,
        provider="cpu",
    )


def create_vad(threshold=None):
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = VAD_MODEL
    config.silero_vad.threshold = VAD_THRESHOLD if threshold is None else threshold
    config.silero_vad.min_silence_duration = END_SILENCE_SECONDS
    config.silero_vad.min_speech_duration = MIN_SPEECH_SECONDS
    config.silero_vad.max_speech_duration = MAX_SPEECH_SECONDS
    config.sample_rate = SAMPLE_RATE
    config.num_threads = 1
    config.provider = "cpu"
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)
    return vad, config.silero_vad.window_size


def record_utterance(state="awake", vad_threshold=None):
    vad, window_size = create_vad(vad_threshold)
    recorder = start_recorder()
    pending = np.empty(0, dtype=np.float32)
    announced = False
    print(f"State: {state}; waiting for human speech.", flush=True)
    try:
        while RUNNING:
            chunk = read_chunk(recorder)
            pending = np.concatenate((pending, samples_from_chunk(chunk)))
            while len(pending) >= window_size:
                vad.accept_waveform(pending[:window_size])
                pending = pending[window_size:]
                if vad.is_speech_detected() and not announced:
                    announced = True
                    print("Human speech detected; recording request.", flush=True)
                if not vad.empty():
                    segment = np.asarray(vad.front.samples, dtype=np.float32)
                    vad.pop()
                    pcm = (np.clip(segment, -1.0, 1.0) * 32767).astype(np.int16)
                    with wave.open(str(REQUEST_AUDIO), "wb") as output:
                        output.setnchannels(CHANNELS)
                        output.setsampwidth(SAMPLE_WIDTH)
                        output.setframerate(SAMPLE_RATE)
                        output.writeframes(pcm.tobytes())
                    return True
    finally:
        stop_recorder(recorder)
    return False


def contains_wake_phrase(text):
    return bool(re.search(r"\bhey\s+val\b", normalized(text)))


def wait_for_wake():
    print('State: sleeping; Whisper-verifying "Hey Val".', flush=True)
    while RUNNING:
        if not record_utterance(state="sleeping", vad_threshold=SLEEP_VAD_THRESHOLD):
            return False
        transcription = transcribe_request()
        if contains_wake_phrase(transcription):
            print("Wake phrase verified.", flush=True)
            return True
        print("Sleeping audio ignored; wake phrase absent.", flush=True)
    return False


def transcribe_request():
    result = subprocess.run(
        [
            "curl", "-fsS", "--url", WHISPER_URL,
            "-F", f"file=@{REQUEST_AUDIO}", "-F", "response_format=json",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    transcription = json.loads(result.stdout)["text"].strip()
    print(f"Sir: {transcription or '[no speech recognized]'}", flush=True)
    report_event("voice.transcribed", characters=len(transcription))
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


def report_event(event, **details):
    try:
        post_json(EVENTS_URL, {"event": event, "details": details}, timeout=5)
    except (urllib.error.URLError, TimeoutError, OSError):
        print(f"Unable to record operational event: {event}", flush=True)


def speak(text):
    print(f"Val: {text}", flush=True)
    speech_text = sanitize_for_speech(text)
    if not speech_text:
        return
    RESPONSE_AUDIO.write_bytes(post_json(PIPER_URL, {"text": speech_text}, timeout=60))
    subprocess.run(["aplay", "-q", "-D", PLAYBACK_DEVICE, str(RESPONSE_AUDIO)], check=True)
    time.sleep(0.25)


def play_thinking_chime():
    if not THINKING_AUDIO.exists():
        frames = []
        for frequency, duration in ((620, 0.08), (0, 0.05), (780, 0.09)):
            count = int(SAMPLE_RATE * duration)
            for index in range(count):
                sample = 0 if frequency == 0 else int(
                    32767 * 0.20 * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)
                )
                frames.append(sample)
        pcm = np.asarray(frames, dtype=np.int16)
        with wave.open(str(THINKING_AUDIO), "wb") as output:
            output.setnchannels(CHANNELS)
            output.setsampwidth(SAMPLE_WIDTH)
            output.setframerate(SAMPLE_RATE)
            output.writeframes(pcm.tobytes())
    subprocess.run(
        ["aplay", "-q", "-D", PLAYBACK_DEVICE, str(THINKING_AUDIO)], check=True
    )


def ask_val(transcription, session_id):
    response = json.loads(post_json(CONTROLLER_URL, {"message": transcription, "source": "voice", "session_id": session_id}, timeout=120))
    return response["response"].strip()


def report_voice_state(state):
    try:
        post_json(VOICE_STATE_URL, {"state": state}, timeout=5)
    except (urllib.error.URLError, TimeoutError, OSError):
        print(f"Unable to report voice state: {state}", flush=True)


def set_voice_state(state):
    global CURRENT_VOICE_STATE
    CURRENT_VOICE_STATE = state
    report_voice_state(state)


def voice_state_heartbeat():
    while RUNNING:
        report_voice_state(CURRENT_VOICE_STATE)
        time.sleep(5)


def normalized(text):
    return re.sub(r"[^a-z0-9%]+", " ", text.lower()).strip()


def is_non_speech(text):
    without_labels = re.sub(r"\[[^]]*\]|\([^)]*\)", " ", text)
    value = normalized(without_labels)
    return not value or value in {"click", "music", "noise", "silence", "blank audio"}


def is_sleep_command(text):
    value = normalized(text)
    return bool(
        re.search(r"\b(?:val|vall|bell)\s+(?:go\s+to\s+)?sleep\b", value)
        or re.fullmatch(r"(?:go\s+to\s+)?sleep", value)
    )


def handle_volume_command(text):
    value = normalized(text)
    match = re.search(r"(?:set\s+)?(?:the\s+)?volume(?:\s+to)?\s+(\d{1,3})", value)
    if match:
        level = max(0, min(100, int(match.group(1))))
        subprocess.run(["amixer", "-q", "-c", "0", "sset", "Master", f"{level}%", "unmute"], check=True)
        return f"Volume set to {level} percent, Sir."
    if re.search(r"\bvolume\s+(?:up|louder)\b", value):
        subprocess.run(["amixer", "-q", "-c", "0", "sset", "Master", "10%+", "unmute"], check=True)
        return "Volume increased, Sir."
    if re.search(r"\bvolume\s+(?:down|quieter)\b", value):
        subprocess.run(["amixer", "-q", "-c", "0", "sset", "Master", "10%-", "unmute"], check=True)
        return "Volume decreased, Sir."
    return None


def main():
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    configure_microphone()
    awake = False
    voice_session_id = None
    print("Val voice service started.", flush=True)
    report_event("voice.started", capture_device=CAPTURE_DEVICE, playback_device=PLAYBACK_DEVICE)
    set_voice_state("sleeping")
    threading.Thread(target=voice_state_heartbeat, daemon=True).start()

    while RUNNING:
        try:
            if not awake:
                if not wait_for_wake():
                    break
                awake = True
                voice_session_id = f"voice-{uuid.uuid4()}"
                set_voice_state("awake")
                report_event("voice.woke", session_id=voice_session_id)
                speak("Yes, Sir?")

            if not record_utterance():
                continue
            transcription = transcribe_request()
            if not transcription or is_non_speech(transcription):
                print("Non-speech audio ignored.", flush=True)
                report_event("voice.non_speech_ignored")
                continue
            if is_sleep_command(transcription):
                speak("Goodnight, Sir.")
                awake = False
                voice_session_id = None
                set_voice_state("sleeping")
                report_event("voice.slept")
                continue
            volume_reply = handle_volume_command(transcription)
            if volume_reply:
                speak(volume_reply)
                continue
            play_thinking_chime()
            answer = ask_val(transcription, voice_session_id)
            if answer:
                speak(answer)
        except (subprocess.SubprocessError, urllib.error.URLError, OSError, ValueError, RuntimeError) as error:
            print(f"Voice loop error: {error}; retrying in 2 seconds.", flush=True)
            report_event("voice.loop_error", error_type=type(error).__name__, message=str(error)[:240])
            time.sleep(2)

    print("Val voice service stopped.", flush=True)


if __name__ == "__main__":
    main()
