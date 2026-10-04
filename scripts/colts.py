"""Colts game-day file: data/colts.json (next game, injury report, headlines).

Daily:  python scripts/colts.py           always refreshes.
Hourly: python scripts/colts.py --hourly  only refreshes on a Colts game day (Eastern time), from midnight until kickoff.
Source is ESPN's public site feed. It is unofficial, so every field is read defensively and a failure leaves the old file alone.
"""
import json, os, sys, urllib.request, datetime as dt
from zoneinfo import ZoneInfo

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "colts.json")
API = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/"
TEAM, TEAM_ID = "IND", "11"
ET = ZoneInfo("America/New_York")
ABBR = {"WSH": "WAS", "LAR": "LA"}
RECORDS = {}

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (our-guys)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def when(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))

def is_game_day_before_kickoff(now):
    try:
        k = when(json.load(open(OUT))["game"]["kickoff"])
    except Exception:
        return False
    return now.astimezone(ET).date() == k.astimezone(ET).date() and now <= k

def record(c):
    rec = c.get("record") or []
    if isinstance(rec, list):
        for r in rec:
            if r.get("type") == "total": return r.get("displayValue") or r.get("summary") or ""
        return (rec[0].get("displayValue") if rec else "") or ""
    return ""

def next_game(now):
    events = get(API + f"teams/{TEAM.lower()}/schedule").get("events") or []
    best = None
    for e in events:
        try: k = when(e["date"])
        except Exception: continue
        # today's game stays "next" all day, even after kickoff
        if k.astimezone(ET).date() >= now.astimezone(ET).date() and (best is None or k < best[0]): best = (k, e)
    if not best: return None
    k, e = best
    comp = (e.get("competitions") or [{}])[0]
    us = opp = {}
    for c in comp.get("competitors") or []:
        if (c.get("team") or {}).get("id") == TEAM_ID or (c.get("team") or {}).get("abbreviation") == TEAM: us = c
        else: opp = c
    ot = opp.get("team") or {}
    venue = comp.get("venue") or {}
    addr = venue.get("address") or {}
    tv = [((b.get("media") or {}).get("shortName") or "") for b in comp.get("broadcasts") or []]
    st = ((comp.get("status") or {}).get("type") or {})
    def score(c):
        s = c.get("score")
        return (s.get("displayValue") if isinstance(s, dict) else s) or ""
    return {
        "id": e.get("id"), "kickoff": k.strftime("%Y-%m-%dT%H:%M:%SZ"), "home": us.get("homeAway") == "home",
        "opp": {"abbr": ABBR.get(ot.get("abbreviation"), ot.get("abbreviation") or ""), "name": ot.get("displayName") or ""},
        "venue": venue.get("fullName") or "", "city": ", ".join(x for x in [addr.get("city"), addr.get("state") or addr.get("country")] if x),
        "tv": ", ".join(t for t in tv if t), "rec": record(us), "opp_rec": record(opp),
        "state": st.get("state") or "", "status": st.get("shortDetail") or st.get("description") or "",
        "score": score(us), "opp_score": score(opp),
    }

def injuries(event_id):
    out = {"ind": [], "opp": []}
    if not event_id: return out
    summary = get(API + f"summary?event={event_id}")
    for c in (((summary.get("header") or {}).get("competitions") or [{}])[0].get("competitors") or []):
        RECORDS["ind" if (c.get("team") or {}).get("id") == TEAM_ID else "opp"] = record(c)
    for block in summary.get("injuries") or []:
        side = "ind" if (block.get("team") or {}).get("id") == TEAM_ID else "opp"
        for i in block.get("injuries") or []:
            a = i.get("athlete") or {}; d = i.get("details") or {}
            detail = " ".join(x for x in [d.get("type"), d.get("detail")] if x and x != "Not Specified")
            out[side].append({"name": a.get("displayName") or "", "pos": (a.get("position") or {}).get("abbreviation") or "",
                              "status": i.get("status") or "", "detail": detail})
    order = {"Out": 0, "Injured Reserve": 1, "Doubtful": 2, "Questionable": 3}
    for side in out: out[side].sort(key=lambda x: (order.get(x["status"], 9), x["name"]))
    return out

def headlines():
    arts = get(API + f"news?team={TEAM_ID}&limit=30").get("articles") or []
    out = []
    for a in arts:
        text = (a.get("headline") or "") + " " + (a.get("description") or "")
        tagged = any(str(c.get("teamId")) == TEAM_ID for c in a.get("categories") or [])
        if "Colts" not in text and not ("Indianapolis" in text) and not (tagged and a.get("type") == "HeadlineNews"): continue
        url = ((a.get("links") or {}).get("web") or {}).get("href")
        if a.get("headline") and url: out.append({"t": a["headline"], "u": url, "d": a.get("published") or ""})
    return out[:8]

def main(hourly=False):
    now = dt.datetime.now(dt.timezone.utc)
    if hourly and not is_game_day_before_kickoff(now):
        print("colts: not a game day before kickoff, nothing to do"); return
    game = next_game(now)
    data = {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "game": game}
    for key, fn in (("injuries", lambda: injuries(game and game.get("id"))), ("headlines", headlines)):
        try: data[key] = fn()
        except Exception as e:
            print("colts:", key, "skipped:", e)
            try: data[key] = json.load(open(OUT)).get(key)
            except Exception: data[key] = None
    if game:
        game["rec"] = game["rec"] or RECORDS.get("ind", ""); game["opp_rec"] = game["opp_rec"] or RECORDS.get("opp", "")
    json.dump(data, open(OUT, "w"), separators=(",", ":"), ensure_ascii=False)
    print("colts:", (game or {}).get("kickoff"), "vs", ((game or {}).get("opp") or {}).get("abbr"), "|", len((data.get("injuries") or {}).get("ind") or []), "Colts injuries |", len(data.get("headlines") or []), "headlines")

if __name__ == "__main__":
    main("--hourly" in sys.argv)
