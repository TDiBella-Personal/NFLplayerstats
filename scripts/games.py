"""This week's NFL games: data/games.json (kickoff, TV, venue, records, injury reports, and a box score once a game is final).

Run by the daily job, and about hourly (--hourly) while a game that has kicked off still has no box score.
The week rolls to the next one once every game is final and the last kickoff was 6+ hours ago. Source is ESPN's public site feed (unofficial), so every field is read defensively
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

def injuries(summary, home_id):
    out = {"home": [], "away": []}
    order = {"Out": 0, "Injured Reserve": 1, "Doubtful": 2, "Questionable": 3}
    for block in summary.get("injuries") or []:
        key = "home" if str((block.get("team") or {}).get("id")) == home_id else "away"
        for i in block.get("injuries") or []:
            a = i.get("athlete") or {}; d = i.get("details") or {}
            detail = " ".join(x for x in [d.get("type"), d.get("detail")] if x and x != "Not Specified")
            out[key].append({"name": a.get("displayName") or "", "pos": (a.get("position") or {}).get("abbreviation") or "", "status": i.get("status") or "", "detail": detail})
    for key in out: out[key].sort(key=lambda x: (order.get(x["status"], 9), x["name"]))
    return out


TEAM_STATS = ["firstDowns", "totalYards", "netPassingYards", "rushingYards", "turnovers", "thirdDownEff", "possessionTime", "totalPenaltiesYards", "sacksYardsLost"]

def leader(groups, name, fmt):
    for grp in groups:
        if grp.get("name") != name: continue
        labels = grp.get("labels") or []
        best = None
        for a in grp.get("athletes") or []:
            st = dict(zip(labels, a.get("stats") or []))
            try: key = float(str(st.get(fmt[0], "0")).split("/")[0])
            except ValueError: key = 0
            if best is None or key > best[0]: best = (key, (a.get("athlete") or {}).get("displayName") or "", st)
        if best and best[1]: return {"n": best[1], "l": fmt[1](best[2])}
    return None

def box(summary, home_id):
    """Score by quarter is added by the caller; this is team totals, leaders and scoring plays."""
    b = summary.get("boxscore") or {}
    out = {"team": {"home": {}, "away": {}}, "lead": {"home": {}, "away": {}}, "plays": []}
    for t in b.get("teams") or []:
        key = "home" if str((t.get("team") or {}).get("id")) == home_id else "away"
        for st in t.get("statistics") or []:
            if st.get("name") in TEAM_STATS and st.get("displayValue") is not None: out["team"][key][st["name"]] = str(st["displayValue"])
    g = lambda st, k: st.get(k, "0")
    fmts = {"pass": ("passing", ("YDS", lambda st: f"{g(st,'C/ATT')}, {g(st,'YDS')} yds, {g(st,'TD')} TD, {g(st,'INT')} INT")),
            "rush": ("rushing", ("YDS", lambda st: f"{g(st,'CAR')} carries, {g(st,'YDS')} yds, {g(st,'TD')} TD")),
            "rec": ("receiving", ("YDS", lambda st: f"{g(st,'REC')} catches, {g(st,'YDS')} yds, {g(st,'TD')} TD")),
            "tkl": ("defensive", ("TOT", lambda st: f"{g(st,'TOT')} tackles" + (f", {g(st,'SACKS')} sack{'' if g(st,'SACKS') in ('1','1.0') else 's'}" if g(st,'SACKS') not in ('0', '0.0', 0) else "")))}
    for t in b.get("players") or []:
        key = "home" if str((t.get("team") or {}).get("id")) == home_id else "away"
        for k, (name, fmt) in fmts.items():
            try:
                l = leader(t.get("statistics") or [], name, fmt)
                if l: out["lead"][key][k] = l
            except Exception as ex: print("games: leader skipped", k, ex)
    for p in summary.get("scoringPlays") or []:
        t = p.get("team") or {}
        out["plays"].append({"q": (p.get("period") or {}).get("number"), "c": (p.get("clock") or {}).get("displayValue") or "",
                             "t": ABBR.get(t.get("abbreviation"), t.get("abbreviation") or ""), "k": (p.get("type") or {}).get("text") or "",
                             "x": p.get("text") or "", "a": p.get("awayScore"), "h": p.get("homeScore")})
    return out

def quarters(c):
    out = []
    for q in c.get("linescores") or []:
        v = q.get("value", q.get("displayValue"))
        try: out.append(int(float(v)))
        except (TypeError, ValueError): out.append(0)
    return out

def main(hourly=False, week=None, out_path=OUT):
    now = dt.datetime.now(dt.timezone.utc)
    try: oldfile = json.load(open(OUT))
    except Exception: oldfile = {}
    old = {g["id"]: g for g in oldfile.get("games", [])}
    if hourly and not any(when(g["kickoff"]) <= now and "box" not in g for g in old.values()):
        print("games: nothing has kicked off without a box score, skipping"); return
    data = get(API + "scoreboard" + (f"?seasontype=2&week={week}" if week else ""))
    events = data.get("events") or []
    wk = (data.get("week") or {}).get("number")
    stype = ((data.get("season") or {}).get("type")) or 2
    if not week and events and wk:
        states = [(((e.get("competitions") or [{}])[0].get("status") or e.get("status") or {}).get("type") or {}).get("state") for e in events]
        try: last = max(when(e["date"]) for e in events)
        except Exception: last = now
        if all(s == "post" for s in states) and (now - last).total_seconds() > 6 * 3600:
            try:
                nxt = get(API + f"scoreboard?seasontype={stype}&week={wk + 1}")
                if nxt.get("events"): data, events, wk = nxt, nxt["events"], wk + 1
            except Exception as ex: print("games: could not load next week,", ex)
    games = []
    for e in events:
        try: k = when(e["date"])
        except Exception: continue
        comp = (e.get("competitions") or [{}])[0]
        home = away = hc = ac = None
        for c in comp.get("competitors") or []:
            if c.get("homeAway") == "home": home, hc = side(c), c
            else: away, ac = side(c), c
        if not home or not away: continue
        venue = comp.get("venue") or {}; addr = venue.get("address") or {}
        st = ((comp.get("status") or e.get("status") or {}).get("type") or {})
        g = {"id": str(e.get("id")), "kickoff": k.strftime("%Y-%m-%dT%H:%M:%SZ"), "home": home, "away": away, "tv": tv(comp),
             "venue": venue.get("fullName") or "", "city": ", ".join(x for x in [addr.get("city"), addr.get("state") or addr.get("country")] if x),
             "state": st.get("state") or "", "status": st.get("shortDetail") or st.get("description") or ""}
        prev = old.get(g["id"], {})
        if g["state"] == "post":
            if "box" in prev: g["box"] = prev["box"]
            else:
                try:
                    g["box"] = box(get(API + f"summary?event={g['id']}"), home["id"])
                    g["box"]["line"] = {"home": quarters(hc), "away": quarters(ac)}
                except Exception as ex: print("games: box score skipped for", g["id"], ex)
        elif g["state"] == "pre" and not hourly:
            try: g["inj"] = injuries(get(API + f"summary?event={g['id']}"), home["id"])
            except Exception as ex: print("games: injuries skipped for", g["id"], ex)
        if "inj" not in g and "inj" in prev: g["inj"] = prev["inj"]
        if g["state"] != "post": g["home"]["score"] = g["away"]["score"] = ""   # finals only, no in-progress scores
        games.append(g)
    if not games:
        print("games: feed returned no games, keeping the old file"); return
    games.sort(key=lambda g: g["kickoff"])
    json.dump({"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "week": wk, "games": games}, open(out_path, "w"), separators=(",", ":"), ensure_ascii=False)
    print("games: week", wk, "-", len(games), "games,", sum(1 for g in games if "inj" in g), "with injury reports,", sum(1 for g in games if "box" in g), "with box scores")

if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if "--week" in a: main(week=int(a[a.index("--week") + 1]), out_path="/tmp/boxtest.json")
    else: main(hourly="--hourly" in a)
