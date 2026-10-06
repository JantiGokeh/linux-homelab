const controllerUrl = 'http://val-controller:8092/chat';

export async function POST(request: Request) {
  try {
    const body = await request.json() as { message?: unknown; session_id?: unknown };
    if (typeof body.message !== 'string' || !body.message.trim()) {
      return Response.json({ error: 'Message is required.' }, { status: 400 });
    }
    if (typeof body.session_id !== 'string' || !/^[A-Za-z0-9_-]{8,80}$/.test(body.session_id)) {
      return Response.json({ error: 'A valid chat session is required.' }, { status: 400 });
    }
    const response = await fetch(controllerUrl, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ message: body.message.trim(), source: 'web', session_id: body.session_id }),
    });
    const data = await response.json();
    return Response.json(data, { status: response.status });
  } catch {
    return Response.json({ error: 'Val is currently unreachable.' }, { status: 503 });
  }
}
