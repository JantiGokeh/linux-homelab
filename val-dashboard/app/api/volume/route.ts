const volumeUrl = 'http://val-controller:8092/volume';

export async function GET() {
  try {
    const response = await fetch(volumeUrl, { signal: AbortSignal.timeout(2500) });
    return Response.json(await response.json(), { status: response.status });
  } catch {
    return Response.json({ error: 'Audio control unavailable.' }, { status: 503 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const response = await fetch(volumeUrl, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    return Response.json(await response.json(), { status: response.status });
  } catch {
    return Response.json({ error: 'Audio control unavailable.' }, { status: 503 });
  }
}
