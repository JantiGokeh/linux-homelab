# Security policy

## Supported version

Only the latest revision of the repository is supported.

## Reporting a vulnerability

Do not open a public issue containing credentials, private network information,
calendar data, or conversation history. Report security concerns privately to
the repository owner.

## Deployment guidance

- Keep the dashboard private or behind an authenticated private network.
- Never publish the model, controller, Whisper, Piper, n8n, or Docker API ports.
- Store service credentials in the service that uses them, not in prompts or
  committed configuration files.
- Review confirmation boundaries before adding any state-changing tool.
- Treat transcripts and calendar results as private data.
