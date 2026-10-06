const voiceStateUrl = 'http://val-controller:8092/voice-state';

export async function GET() {
  try {
    const response = await fetch(voiceStateUrl, { cache: 'no-store', signal: AbortSignal.timeout(3000) });
    return Response.json(await response.json(), { status: response.status });
  } catch {
    return Response.json({ state: 'unknown', updated_at: null }, { status: 503 });
  }
}
