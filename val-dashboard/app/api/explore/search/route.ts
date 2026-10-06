const searchUrl = 'http://val-controller:8092/explore/search';

export async function POST(request: Request) {
  try {
    const body = await request.json() as { query?: unknown };
    if (typeof body.query !== 'string' || !body.query.trim() || body.query.trim().length > 160) {
      return Response.json({ error: 'Enter a search between 1 and 160 characters.' }, { status: 400 });
    }
    const response = await fetch(searchUrl, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ query: body.query.trim() }), signal: AbortSignal.timeout(25000),
    });
    return Response.json(await response.json(), { status: response.status });
  } catch {
    return Response.json({ error: 'Web search is currently unavailable.' }, { status: 503 });
  }
}
