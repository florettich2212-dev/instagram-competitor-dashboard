export default {
  async fetch(request, env) {
    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Content-Type': 'application/json',
    };

    if (request.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (request.method !== 'POST') return new Response(JSON.stringify({ error: 'POST only' }), { status: 405, headers: cors });

    let username = null;
    try {
      const body = await request.json();
      username = body.username || null;
    } catch {}

    const workflow = username ? 'scrape_account.yml' : 'scrape.yml';
    const payload  = username
      ? { ref: 'main', inputs: { username } }
      : { ref: 'main' };

    const res = await fetch(
      `https://api.github.com/repos/florettich2212-dev/instagram-competitor-dashboard/actions/workflows/${workflow}/dispatches`,
      {
        method: 'POST',
        headers: {
          Authorization: `token ${env.GH_TOKEN}`,
          Accept: 'application/vnd.github.v3+json',
          'Content-Type': 'application/json',
          'User-Agent': 'leonie-dashboard-worker',
        },
        body: JSON.stringify(payload),
      }
    );

    if (res.status === 204) return new Response(JSON.stringify({ status: 'triggered' }), { headers: cors });

    const body = await res.text();
    return new Response(JSON.stringify({ error: 'GitHub error', status: res.status, body }), { status: 502, headers: cors });
  },
};
