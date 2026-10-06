const whisperUrl = 'http://val-whisper:8080/inference';
const maxAudioBytes = 15 * 1024 * 1024;
const allowedAudioTypes = new Set([
  'audio/webm',
  'audio/ogg',
  'audio/mp4',
  'audio/wav',
  'audio/x-wav',
]);

export async function POST(request: Request) {
  try {
    const contentLength = Number(request.headers.get('content-length') ?? '0');
    if (contentLength > maxAudioBytes + 1024 * 1024) {
      return Response.json({ error: 'The recording is too large.' }, { status: 413 });
    }

    const incoming = await request.formData();
    const audio = incoming.get('file');
    if (!(audio instanceof File) || audio.size === 0) {
      return Response.json({ error: 'An audio recording is required.' }, { status: 400 });
    }
    if (audio.size > maxAudioBytes) {
      return Response.json({ error: 'The recording is too large.' }, { status: 413 });
    }

    const baseType = audio.type.split(';', 1)[0].toLowerCase();
    if (!allowedAudioTypes.has(baseType)) {
      return Response.json({ error: 'This audio format is not supported.' }, { status: 415 });
    }

    const body = new FormData();
    body.append('file', audio, audio.name || 'browser-recording');
    body.append('response_format', 'json');
    body.append('language', 'en');

    const response = await fetch(whisperUrl, { method: 'POST', body });
    const data = await response.json() as { text?: unknown; error?: unknown };
    if (!response.ok) {
      return Response.json({ error: typeof data.error === 'string' ? data.error : 'Transcription failed.' }, { status: response.status });
    }

    const text = typeof data.text === 'string' ? data.text.trim() : '';
    if (!text) {
      return Response.json({ error: 'No speech was detected.' }, { status: 422 });
    }
    return Response.json({ text });
  } catch {
    return Response.json({ error: 'Speech recognition is currently unavailable.' }, { status: 503 });
  }
}
