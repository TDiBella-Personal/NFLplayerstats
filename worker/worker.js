// Our Guys backend. One Cloudflare Worker, one KV namespace (binding: OG), one secret (ANTHROPIC_API_KEY).
// Vars: PAGES_ORIGIN (e.g. https://tdibella-personal.github.io), optional MODEL, DAILY_STORY_CAP, DAILY_ASK_CAP.
//
// GET  /favs            -> ["00-0036223", ...]
// PUT  /favs            <- same array
// GET  /theme           -> {team:"IND"}   PUT /theme <- same ("" = no team)
// GET  /story/:id       -> {bullets:[...], hometown:"..."} or 404
// POST /story/:id       <- {name, team, pos, college, drafted}  researches, saves, returns the story
// POST /ask             <- {q}  answers a rules/terms question, saves it, returns {q, title, cat, short, deep}
// GET  /ask/:key        -> saved answer or 404
// GET  /asks            -> recent questions [{q, key, title, short, at}]

const DEFAULT_MODEL = "claude-sonnet-5-5";

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const origin = req.headers.get("Origin") || "";
    const allowed = (env.PAGES_ORIGIN || "").split(",").map(s => s.trim().replace(/\/$/, "")).filter(Boolean);
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

      if (url.pathname === "/theme") {
        if (req.method === "GET") return json((await env.OG.get("theme", "json")) || { team: "IND" });
        if (req.method === "PUT") {
          const body = await req.json();
          const team = String(body.team || "");
          if (!/^[A-Z]{0,3}$/.test(team)) return json({ error: "bad team" }, 400);
          await env.OG.put("theme", JSON.stringify({ team }));
          return json({ team });
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
          if (!(await underCap(env, "story", Number(env.DAILY_STORY_CAP || 40)))) return json({ error: "daily limit reached, try tomorrow" }, 429);
          const p = await req.json();
          const story = await research(p, env);
          await env.OG.put(key, JSON.stringify(story));
          return json(story);
        }
      }

      if (url.pathname === "/asks" && req.method === "GET") {
        return json((await env.OG.get("asks:recent", "json")) || []);
      }
      const a = url.pathname.match(/^\/ask\/([\w-]+)$/);
      if (a && req.method === "GET") {
        const s = await env.OG.get("ask:" + a[1], "json");
        return s ? json(s) : json({ error: "not asked yet" }, 404);
      }
      if (url.pathname === "/ask" && req.method === "POST") {
        const body = await req.json();
        const q = String(body.q || "").trim().slice(0, 200);
        if (q.length < 2) return json({ error: "ask a question" }, 400);
        const k = askKey(q);
        const cached = await env.OG.get("ask:" + k, "json");
        if (cached) return json(cached);
        if (!(await underCap(env, "ask", Number(env.DAILY_ASK_CAP || 80)))) return json({ error: "daily limit reached, try tomorrow" }, 429);
        const ans = await answer(q, env);
        ans.key = k;
        if (!ans.ok) return json(ans);  // don't save a failed answer
        delete ans.ok;
        await env.OG.put("ask:" + k, JSON.stringify(ans));
        const recent = ((await env.OG.get("asks:recent", "json")) || []).filter(r => r.key !== k);
        recent.unshift({ q: ans.q, key: k, title: ans.title, short: ans.short, at: ans.at });
        await env.OG.put("asks:recent", JSON.stringify(recent.slice(0, 40)));
        return json(ans);
      }

      return json({ error: "not found" }, 404);
    } catch (e) {
      return json({ error: String(e.message || e) }, 500);
    }
  },
};

function askKey(q) {
  return q.toLowerCase().replace(/['’]/g, "").replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim().replace(/ /g, "-").slice(0, 120) || "q";
}

async function underCap(env, kind, cap) {
  const day = new Date().toISOString().slice(0, 10);
  const k = `cap:${kind}:${day}`;
  const used = Number((await env.OG.get(k)) || 0);
  if (used >= cap) return false;
  await env.OG.put(k, String(used + 1), { expirationTtl: 172800 });
  return true;
}

async function callClaude(prompt, env, maxUses) {
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: env.MODEL || DEFAULT_MODEL,
      max_tokens: 1500,
      messages: [{ role: "user", content: prompt }],
      tools: [{ type: "web_search_20250305", name: "web_search", max_uses: maxUses }],
    }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error?.message || "anthropic " + r.status);
  const text = (data.content || []).filter(b => b.type === "text").map(b => b.text).join("\n");
  const start = text.indexOf("{"), end = text.lastIndexOf("}");
  if (start >= 0 && end > start) {
    try { return JSON.parse(text.slice(start, end + 1)); } catch {}
  }
  return {};
}

const clean = s => String(s || "").replace(/\s*—\s*/g, ", ").trim();

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
  const out = await callClaude(prompt, env, 5);
  return {
    hometown: clean(out.hometown).slice(0, 80),
    bullets: (Array.isArray(out.bullets) ? out.bullets : []).slice(0, 4).map(s => clean(s).slice(0, 220)),
    at: new Date().toISOString(),
  };
}

async function answer(q, env) {
  const year = new Date().getUTCFullYear();
  const prompt = `Two people are watching an NFL game on TV and one of them just asked: "${q}"

Answer it for them. One is a newer fan, the other is learning schemes.

Rules:
- If the question is about an NFL rule, penalty, clock, replay, kickoff, overtime or anything that could have changed recently, use web search to confirm the CURRENT ${year} NFL rule before answering. Do not rely on memory for rules.
- If it's announcer slang or a scheme term, explain what announcers mean by it. Search if you're not sure.
- If it isn't about football, say so in the short answer and leave deep empty.
- Plain English. No em dashes. No hype. Don't mention sources or searching in the text.

Respond with ONLY a JSON object, no markdown fences, no preamble:
{"title":"2-5 word name of the thing","cat":"penalty|rule|offense|defense|position|lingo|other","short":"ONE sentence, max 30 words, the answer a newer fan gets","deep":["3 to 5 bullets for the scheme nerd, each max 35 words: details, variants, why it matters, how it plays out"]}`;
  const out = await callClaude(prompt, env, 4);
  return {
    ok: !!clean(out.short),
    q,
    title: clean(out.title).slice(0, 60) || q,
    cat: ["penalty", "rule", "offense", "defense", "position", "lingo", "other"].includes(out.cat) ? out.cat : "other",
    short: clean(out.short).slice(0, 300) || "Couldn't get a clean answer on that one. Try rewording it.",
    deep: (Array.isArray(out.deep) ? out.deep : []).slice(0, 5).map(s => clean(s).slice(0, 260)),
    at: new Date().toISOString(),
  };
}
