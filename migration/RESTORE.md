# Migration and restore

This repository contains application source and example configuration. Runtime
state, credentials, model files, audio configuration, and conversation history
are deliberately excluded.

## Before moving hosts

Create private, encrypted backups of:

- `data/`
- `models/`
- the active `.env`
- n8n workflows, database, and encryption configuration
- any customized persona or tool configuration

Stop n8n before copying its database. Do not add any of these private backups to
the Git repository.

## Restore outline

1. Install Docker Engine and Docker Compose on the replacement Linux host.
2. Clone this repository and copy `.env.example` to `.env`.
3. Restore the private model and runtime-data directories.
4. Restore n8n separately and start it before Val if the n8n tools are enabled.
5. Review CPU threads, memory limits, audio devices, the audio-group ID, local
   timezone, model filename, and dashboard binding in `.env` and `compose.yaml`.
6. Start Val with `docker compose up -d --build`.
7. Recreate the host-status scheduled job with paths appropriate for the new
   installation directory.
8. Re-enroll the host in the chosen private remote-access system.
9. Test speech recognition, synthesis, wake detection, the controller, tools,
   dashboard, transcripts, microphone capture, and speaker playback.

Hardware-specific audio names, network addresses, scheduled jobs, and CPU/GPU
settings must be reviewed on every replacement host.
