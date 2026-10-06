const historyUrl = 'http://val-controller:8092/history';

export async function GET() {
  try {
    const response = await fetch(historyUrl, { cache: 'no-store', signal: AbortSignal.timeout(3000) });
    return Response.json(await response.json(), { status: response.status });
  } catch {
    return Response.json({ conversations: [], error: 'Transcript service unavailable.' }, { status: 503 });
  }
}
