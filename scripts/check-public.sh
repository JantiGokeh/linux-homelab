#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

blocked='(BEGIN (RSA |OPENSSH )?PRIVATE KEY|client_secret[[:space:]]*[:=]|api[_-]?key[[:space:]]*[:=]|password[[:space:]]*[:=][[:space:]]*"[^"]+|192\.168\.|/home/[A-Za-z0-9._-]+|[A-Za-z0-9-]+\.ts\.net|CODEX_SANDBOX|@openai/sites-vite-plugin)'

cd "$root"
if git ls-files -z | grep -zv '^scripts/check-public.sh$' | xargs -0 -r grep -nE -- "$blocked"; then
  echo "Public-readiness check failed: private or development-specific content found." >&2
  exit 1
fi

echo "Public-readiness check passed."
