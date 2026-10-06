# Linux Homelab Infrastructure

This repository contains the public source for a Linux homelab service stack
built around a self-hosted voice assistant. It uses Docker Compose to run local
speech recognition, language-model inference, text-to-speech, a controller,
and a web dashboard on modest home-server hardware. It also includes a Python
host-status collector, GitHub Actions checks, and migration notes. Private
configuration, model files, credentials, and runtime data are excluded.

## Features

- Always-listening wake phrase and explicit sleep phrase
- Local Whisper speech recognition and Piper speech synthesis
- Local GGUF language model served by llama.cpp
- Typed chat, browser dictation, transcripts, volume control, and Explore views
- Read-only weather, calendar, news, web-search, and server-status tools
- Controller-owned tool allowlist with argument and response validation
- Private-by-default service bindings and support for Tailscale Serve

## Architecture

```text
Room microphone -> wake/VAD -> Whisper -> controller -> llama.cpp
                                        |          -> approved tools / n8n
                                        -> Piper -> speakers

Browser -> dashboard -> controller / Whisper
```

The model never receives unrestricted shell access, raw credentials, or a
Docker socket. State-changing tools are intentionally not included in this
public version.

## Requirements

- Linux host with Docker Engine and Docker Compose
- Approximately 8 GiB RAM for the provided 4B-model configuration
- ALSA-compatible microphone and speakers for room voice mode
- An existing Docker network named `n8n_default` if the n8n tools are enabled

## Setup

1. Copy the example environment file and adjust it for your host:

   ```bash
   cp .env.example .env
   ```

2. Create `models/` and place these files in it:

   - A llama.cpp-compatible GGUF model matching `VAL_MODEL_FILE`
   - `ggml-base.en.bin` for Whisper
   - The Piper voice files for `en_GB-alba-medium`
   - A Silero VAD ONNX model at `models/vad/silero_vad.onnx`
   - A sherpa-onnx keyword-spotting model under `models/wake/`

3. Review `config/persona.txt` and `config/tools.json`.

4. If using the n8n workflows, import the JSON files from `n8n/`, replace all
   placeholder values, select your own Google credential, and confirm that the
   webhook paths match `config/tools.json`.

5. Start the stack:

   ```bash
   docker compose up -d --build
   ```

6. Check the dashboard at `http://127.0.0.1:8090`. Browser microphone capture
   requires localhost or trusted HTTPS. For remote access, prefer private
   Tailscale Serve instead of router port forwarding or Tailscale Funnel.

## Security

- Do not commit `.env`, `models/`, `data/`, n8n state, transcripts, or keys.
- The dashboard binds to localhost by default.
- Keep model, controller, Whisper, and Piper ports bound to localhost.
- Review every imported n8n workflow before activation.
- Do not expose the Docker socket to Val.

See [SECURITY.md](SECURITY.md) for reporting and deployment guidance.

## Testing

```bash
python3 -m unittest discover -s controller -p 'test_*.py'
python3 -m unittest discover -s voice -p 'test_*.py'
docker compose config
cd val-dashboard
npm ci
npm run typecheck
npm run build
```

## Project status

This repository contains the read-only-tool prototype. Calendar writes,
long-term memory, unrestricted server administration, and full-duplex audio are
not implemented.
