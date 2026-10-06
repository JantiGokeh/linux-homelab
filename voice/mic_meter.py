import math
import os
import subprocess
import time

import numpy as np


device = os.environ.get("VAL_AUDIO_DEVICE", "plughw:0,0")
seconds = int(os.environ.get("VAL_METER_SECONDS", "15"))
sample_rate = 16000
chunk_bytes = 3200
levels = []

recorder = subprocess.Popen(
    [
        "arecord", "-q", "-D", device, "-t", "raw", "-f", "S16_LE",
        "-r", str(sample_rate), "-c", "1",
    ],
    stdout=subprocess.PIPE,
)

print(f"Measuring microphone for {seconds} seconds. Speak now.", flush=True)
try:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        chunk = recorder.stdout.read(chunk_bytes)
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float64)
        rms = math.sqrt(float(np.mean(samples * samples))) if samples.size else 0.0
        levels.append(rms)
finally:
    recorder.terminate()
    recorder.wait(timeout=3)

ordered = sorted(levels)
ambient = ordered[len(ordered) // 2] if ordered else 0
high = ordered[int(len(ordered) * 0.95)] if ordered else 0
peak = max(ordered, default=0)
print(f"MIC_LEVELS ambient_rms={ambient:.0f} speech_rms_95={high:.0f} peak_rms={peak:.0f}", flush=True)
