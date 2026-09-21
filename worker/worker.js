// Our Guys backend. One Cloudflare Worker, one KV namespace (binding: OG), one secret (ANTHROPIC_API_KEY).
// Vars: PAGES_ORIGIN (e.g. https://tdibella-personal.github.io), optional MODEL, optional DAILY_STORY_CAP.
//
// GET  /favs            -> ["00-0036223", ...]
// PUT  /favs            <- same array
// GET  /story/:id       -> {bullets:[...], hometown:"..."} or 404
// POST /story/:id       <- {name, team, pos, college, drafted}  researches, saves, returns the story

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const origin = req.headers.get("Origin") || "";
    const allowed = (env.PAGES_ORIGIN || "").split(",").map(s => s.trim()).filter(Boolean);
    const ok = allowed.length === 0 || allowed.includes(origin) || origin.startsWith("http://localhost");
    const cors = {
      "Access-Control-Allow-Origin": ok ? origin || "*" : "null",
      "Access-Control-Allow-Methods": "GET,PUT,POST,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Content-Type": "application/json",
    };
    const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: cors });
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    if (!ok) return json({ error: "origin not allowed" }, 403);

    try {
      if (url.pathname === "/favs") {
        if (req.method === "GET") return json((await env.OG.get("favs", "json")) || []);
        if (req.method === "PUT") {
          const body = await req.json();
          if (!Array.isArray(body) || body.length > 200) return json({ error: "bad list" }, 400);
          await env.OG.put("favs", JSON.stringify(body.map(String)));
          return json(body);
        }
      }
      const m = url.pathname.match(/^\/story\/([\w-]+)$/);
      if (m) {
        const key = "story:" + m[1];
        if (req.method === "GET") {
          const s = await env.OG.get(key, "json");
          return s ? json(s) : json({ error: "no story yet" }, 404);
        }
        if (req.method === "POST") {
          const existing = await env.OG.get(key, "json");
          if (existing) return json(existing);
          const day = new Date().toISOString().slice(0, 10);
          const used = Number((await env.OG.get("cap:" + day)) || 0);
          if (used >= Number(env.DAILY_STORY_CAP || 40)) return json({ error: "daily limit reached, try tomorrow" }, 429);
          await env.OG.put("cap:" + day, String(used + 1), { expirationTtl: 172800 });
          const p = await req.json();
          const story = await research(p, env);
          await env.OG.put(key, JSON.stringify(story));
          return json(story);
        }
      }
      return json({ error: "not found" }, 404);
    } catch (e) {
      return json({ error: String(e.message || e) }, 500);
    }
  },
};

async function research(p, env) {
  const prompt = `You are researching NFL player ${p.name}, ${p.pos}, ${p.team}. College: ${p.college}. Drafted: ${p.drafted}.

Use web search to find his personal story: adversity overcome, family, hardship, dedication, community work, unusual path to the NFL. This is for two fans on a couch who want the human side, not the stats.

Rules:
- Only include facts you actually found in a source. Never guess or embellish. He is a real person.
- If you cannot find anything solid and specific about his personal story, return an empty bullets array. That is a fine answer.
- 3 to 4 bullets max, each ONE plain sentence, no more than 25 words, no source names or URLs in the text.
- Also return his hometown (city, state) if a source states it, otherwise an empty string.

Respond with ONLY a JSON object, no markdown fences, no preamble:
{"hometown":"...","bullets":["...","..."]}`;

  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: env.MODEL || "claude-sonnet-4-6",
      max_tokens: 1500,
      messages: [{ role: "user", content: prompt }],
      tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 5 }],
    }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error?.message || "anthropic " + r.status);
  const text = (data.content || []).filter(b => b.type === "text").map(b => b.text).join("\n");
  const start = text.indexOf("{"), end = text.lastIndexOf("}");
  let out = { hometown: "", bullets: [] };
  if (start >= 0 && end > start) {
    try { out = JSON.parse(text.slice(start, end + 1)); } catch {}
  }
  return {
    hometown: String(out.hometown || "").slice(0, 80),
    bullets: (Array.isArray(out.bullets) ? out.bullets : []).slice(0, 4).map(s => String(s).slice(0, 220)),
    at: new Date().toISOString(),
  };
}
