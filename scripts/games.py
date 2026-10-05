"""This week's NFL games: data/games.json (kickoff, TV, venue, records, and injury reports for today's games).

Run by the daily job. Source is ESPN's public site feed (unofficial), so every field is read defensively
and a failure leaves the old file alone.
"""
import json, os, urllib.request, datetime as dt
from zoneinfo import ZoneInfo

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "games.json")
API = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/"
ET = ZoneInfo("America/New_York")
ABBR = {"WSH": "WAS", "LAR": "LA"}

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (our-guys)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def when(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))

def record(c):
    for key in ("records", "record"):
        rec = c.get(key) or []
        if isinstance(rec, list) and rec:
            for r in rec:
                if r.get("type") == "total" or r.get("name") == "overall": return r.get("summary") or r.get("displayValue") or ""
            return rec[0].get("summary") or rec[0].get("displayValue") or ""
    return ""

def side(c):
    t = c.get("team") or {}
    s = c.get("score")
    return {"abbr": ABBR.get(t.get("abbreviation"), t.get("abbreviation") or ""), "name": t.get("displayName") or "", "id": str(t.get("id") or ""),
            "rec": record(c), "score": (s.get("displayValue") if isinstance(s, dict) else s) or ""}

def tv(comp):
    out = []
    for b in comp.get("broadcasts") or []:
        names = b.get("names") or ([(b.get("media") or {}).get("shortName")] if b.get("media") else [])
        out += [x for x in names if x]
    for b in comp.get("geoBroadcasts") or []:
        x = (b.get("media") or {}).get("shortName")
        if x and (b.get("type") or {}).get("shortName") in ("TV", "Streaming", None): out.append(x)
    seen = []
    for x in out:
        if x not in seen: seen.append(x)
    return ", ".join(seen[:3])

def injuries(event_id, home_id):
    out = {"home": [], "away": []}
    order = {"Out": 0, "Injured Reserve": 1, "Doubtful": 2, "Questionable": 3}
    for block in get(API + f"summary?event={event_id}").get("injuries") or []:
        key = "home" if str((block.get("team") or {}).get("id")) == home_id else "away"
        for i in block.get("injuries") or []:
            a = i.get("athlete") or {}; d = i.get("details") or {}
            detail = " ".join(x for x in [d.get("type"), d.get("detail")] if x and x != "Not Specified")
            out[key].append({"name": a.get("displayName") or "", "pos": (a.get("position") or {}).get("abbreviation") or "", "status": i.get("status") or "", "detail": detail})
    for key in out: out[key].sort(key=lambda x: (order.get(x["status"], 9), x["name"]))
    return out

def main():
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(ET).date()
    try: old = {g["id"]: g for g in json.load(open(OUT)).get("games", [])}
    except Exception: old = {}
    games = []
    for e in get(API + "scoreboard").get("events") or []:
        try: k = when(e["date"])
        except Exception: continue
        comp = (e.get("competitions") or [{}])[0]
        home = away = None
        for c in comp.get("competitors") or []:
            if c.get("homeAway") == "home": home = side(c)
            else: away = side(c)
        if not home or not away: continue
        venue = comp.get("venue") or {}; addr = venue.get("address") or {}
        st = ((comp.get("status") or e.get("status") or {}).get("type") or {})
        g = {"id": str(e.get("id")), "kickoff": k.strftime("%Y-%m-%dT%H:%M:%SZ"), "home": home, "away": away, "tv": tv(comp),
             "venue": venue.get("fullName") or "", "city": ", ".join(x for x in [addr.get("city"), addr.get("state") or addr.get("country")] if x),
             "state": st.get("state") or "", "status": st.get("shortDetail") or st.get("description") or ""}
        if k.astimezone(ET).date() == today:
            try: g["inj"] = injuries(g["id"], home["id"])
            except Exception as ex:
                print("games: injuries skipped for", g["id"], ex)
                if "inj" in old.get(g["id"], {}): g["inj"] = old[g["id"]]["inj"]
        elif "inj" in old.get(g["id"], {}): g["inj"] = old[g["id"]]["inj"]
        games.append(g)
    if not games:
        print("games: feed returned no games, keeping the old file"); return
    games.sort(key=lambda g: g["kickoff"])
    json.dump({"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "games": games}, open(OUT, "w"), separators=(",", ":"), ensure_ascii=False)
    print("games:", len(games), "this week,", sum(1 for g in games if "inj" in g), "with injury reports")

if __name__ == "__main__":
    main()
