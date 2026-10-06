const checks = [
  ['model', 'http://val-model:8080/health'],
  ['controller', 'http://val-controller:8092/health'],
  ['whisper', 'http://val-whisper:8080/'],
  ['piper', 'http://val-piper:5000/voices'],
] as const;

export async function GET() {
  const results = await Promise.all(checks.map(async ([name, url]) => {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(2500) });
      return [name, response.ok] as const;
    } catch {
      return [name, false] as const;
    }
  }));
  return Response.json({ services: Object.fromEntries(results) });
}
