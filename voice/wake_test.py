import os
import subprocess
import time

import numpy as np
import sherpa_onnx


MODEL_DIR = os.environ.get(
    "VAL_WAKE_MODEL_DIR",
    "/models/wake/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01",
)
AUDIO_DEVICE = os.environ.get("VAL_AUDIO_DEVICE", "plughw:0,0")
TIMEOUT_SECONDS = int(os.environ.get("VAL_WAKE_TEST_SECONDS", "30"))


def main():
    spotter = sherpa_onnx.KeywordSpotter(
        tokens=f"{MODEL_DIR}/tokens.txt",
        encoder=f"{MODEL_DIR}/encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
        decoder=f"{MODEL_DIR}/decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
        joiner=f"{MODEL_DIR}/joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
        num_threads=1,
        max_active_paths=4,
        keywords_file=f"{MODEL_DIR}/hey-val.txt",
        keywords_score=3.0,
        keywords_threshold=0.25,
        num_trailing_blanks=1,
        provider="cpu",
    )
    stream = spotter.create_stream()
    recorder = subprocess.Popen(
        [
            "arecord", "-q", "-D", AUDIO_DEVICE, "-t", "raw", "-f", "S16_LE",
            "-r", "16000", "-c", "1",
        ],
        stdout=subprocess.PIPE,
    )

    print(f'Listening for "Hey Val" for {TIMEOUT_SECONDS} seconds...', flush=True)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        while time.monotonic() < deadline:
            audio = recorder.stdout.read(3200)
            if not audio:
                raise RuntimeError("Microphone stream ended unexpectedly")
            samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
            stream.accept_waveform(16000, samples)
            while spotter.is_ready(stream):
                spotter.decode_stream(stream)
            result = spotter.get_result(stream)
            if result:
                print(f"DETECTED: {result}", flush=True)
                return
        raise RuntimeError('Timed out without detecting "Hey Val"')
    finally:
        recorder.terminate()
        recorder.wait(timeout=5)


if __name__ == "__main__":
    main()
