const newsUrl = 'http://val-controller:8092/explore/news';

export async function POST() {
  try {
    const response = await fetch(newsUrl, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}', signal: AbortSignal.timeout(25000),
    });
    return Response.json(await response.json(), { status: response.status });
  } catch {
    return Response.json({ error: 'News is currently unavailable.' }, { status: 503 });
  }
}
