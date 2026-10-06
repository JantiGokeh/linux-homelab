# Architecture

## Services

- `val-model`: llama.cpp OpenAI-compatible chat endpoint
- `val-controller`: persona, recent context, transcripts, tool routing, and API
- `val-whisper`: local speech-to-text service
- `val-piper`: local text-to-speech service
- `val-voice`: wake phrase, voice activity detection, recording, and playback
- `val-dashboard`: typed chat, browser dictation, history, settings, and Explore

## Trust boundaries

The controller owns the tool registry. Tool requests are validated against a
fixed schema before any network call. Tool responses must be bounded JSON
objects with an explicit successful status. Browser audio is limited in size
and duration before it is sent to Whisper.

The host-status collector writes a narrow JSON snapshot. The controller reads
that snapshot instead of receiving the Docker socket or general shell access.

## Persistent data

Runtime data belongs under `data/` and is excluded from version control. It can
include transcripts, settings, operation logs, status snapshots, and cached
Explore results. Audio recordings are temporary and should not be retained.
