const exploreUrl = 'http://val-controller:8092/explore';

export async function GET() {
  try {
    const response = await fetch(exploreUrl, { cache: 'no-store', signal: AbortSignal.timeout(3000) });
    return Response.json(await response.json(), { status: response.status });
  } catch {
    return Response.json({ news: null, search: null, error: 'Explore is currently unavailable.' }, { status: 503 });
  }
}
