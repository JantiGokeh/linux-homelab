import json
import time
import urllib.request
import os
from pathlib import Path


persona = Path(os.environ.get("VAL_PERSONA_PATH", "config/persona.txt")).read_text(encoding="utf-8")
tests = [
    "What is two plus two? Answer in one short sentence.",
    "Describe who you are and who owns you. Answer in two short sentences.",
]

for name, port in (("candidate-1.7B", 8095),):
    print(f"\n{name}")
    for prompt in tests:
        test_prompt = f"/no_think\n{prompt}" if name == "candidate-1.7B" else prompt
        payload = {
            "messages": [
                {"role": "system", "content": persona},
                {"role": "user", "content": test_prompt},
            ],
            "max_tokens": 100,
            "temperature": 0.3,
        }
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        start = time.monotonic()
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
        elapsed = time.monotonic() - start
        message = result["choices"][0]["message"]["content"].strip()
        speed = result.get("timings", {}).get("predicted_per_second", 0)
        print(f"{elapsed:.2f}s, {speed:.2f} generated tokens/s: {message}")
