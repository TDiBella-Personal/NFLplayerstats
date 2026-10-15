"""Turns data/_legends_raw.json (Wikipedia infoboxes, fetched by fetch_legends_wiki.py in Actions) into legend
entries in data/retired.json, for stars whose careers ended before the stats data starts (1999).

Only numbers that appear in the infobox are used; nothing is estimated. Run: python3 scripts/add_old_legends.py
then python3 scripts/build_awards.py (so award badges and the stars list pick the new players up).
"""
import csv, json, os, re, sys, urllib.request, io
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "..", "data")
PLAYERS = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"

LABELS = {
    "games played": "gp", "games": "gp", "passing yards": "passing_yards", "passing attempts": "attempts", "pass attempts": "attempts",
    "passing completions": "completions", "pass completions": "completions", "completions": "completions",
    "passer rating": "rating", "rushing yards": "rushing_yards", "rushing attempts": "carries", "rushing touchdowns": "rushing_tds",
    "receptions": "receptions", "receiving yards": "receiving_yards", "receiving touchdowns": "receiving_tds",
    "sacks": "def_sacks", "interceptions": "def_interceptions", "tackles": "tackles", "total tackles": "tackles",
    "forced fumbles": "def_fumbles_forced", "field goals made": "fg_made", "field goal attempts": "fg_att", "field goals attempted": "fg_att",
    "extra points made": "pat_made", "extra point attempts": "pat_att", "extra points attempted": "pat_att", "points scored": "points",
    "punts": "pt_att", "punting yards": "pt_yds", "punting average": "pt_avg", "punt average": "pt_avg", "average punt": "pt_avg", "longest punt": "pt_long",
}
TEAM = {"Chicago Bears": "CHI", "Pittsburgh Steelers": "PIT", "Dallas Cowboys": "DAL", "San Francisco 49ers": "SF", "Kansas City Chiefs": "KC",
    "New York Giants": "NYG", "New York Jets": "NYJ", "Minnesota Vikings": "MIN", "Miami Dolphins": "MIA", "Green Bay Packers": "GB",
    "Detroit Lions": "DET", "Denver Broncos": "DEN", "Cleveland Browns": "CLE", "Cincinnati Bengals": "CIN", "Buffalo Bills": "BUF",
    "Philadelphia Eagles": "PHI", "Atlanta Falcons": "ATL", "New Orleans Saints": "NO", "Tampa Bay Buccaneers": "TB", "Seattle Seahawks": "SEA",
    "Washington Redskins": "WAS", "Washington Commanders": "WAS", "Houston Oilers": "TEN", "Tennessee Oilers": "TEN", "Tennessee Titans": "TEN",
    "Baltimore Colts": "IND", "Indianapolis Colts": "IND", "Oakland Raiders": "LV", "Los Angeles Raiders": "LV", "Las Vegas Raiders": "LV",
    "San Diego Chargers": "LAC", "Los Angeles Chargers": "LAC", "Los Angeles Rams": "LA", "St. Louis Rams": "LA", "St. Louis Cardinals": "ARI",
    "Phoenix Cardinals": "ARI", "Arizona Cardinals": "ARI", "New England Patriots": "NE", "Boston Patriots": "NE", "Carolina Panthers": "CAR",
    "Jacksonville Jaguars": "JAX", "Baltimore Ravens": "BAL", "Houston Texans": "HOU"}
POS = {"running back": "RB", "fullback": "RB", "halfback": "RB", "quarterback": "QB", "wide receiver": "WR", "split end": "WR", "flanker": "WR",
    "tight end": "TE", "defensive tackle": "DL", "nose tackle": "DL", "defensive end": "EDGE", "linebacker": "LB", "outside linebacker": "LB",
    "middle linebacker": "LB", "cornerback": "CB", "safety": "S", "free safety": "S", "strong safety": "S", "placekicker": "K", "kicker": "K",
    "punter": "P", "center": "OL", "guard": "OL", "offensive tackle": "OL", "tackle": "OL", "offensive guard": "OL", "defensive back": "DB"}

def plain(s):
    s = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    return re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ").strip()

def num(v):
    v = plain(v).replace(",", "").replace("½", ".5").replace("−", "-").strip()
    m = re.match(r"^-?\d+(\.\d+)?", v)
    if not m: return None
    x = float(m.group(0))
    return int(x) if x == int(x) and "." not in m.group(0) else x

import unicodedata
NICK = {"Joe Greene": "mean joe greene", "Walter Payton": "sweetness", "Joe Montana": "joe cool", "Lawrence Taylor": "LT",
        "Joe Namath": "broadway joe", "Ken Stabler": "the snake", "Earl Campbell": "tyler rose", "Too Tall Jones": "ed too tall jones",
        "Deacon Jones": "secretary of defense", "Fran Tarkenton": "scramblin fran", "Jack Lambert": "jack splat", "Ed Jones": ""}
ALIAS = {"jimbo covert": "jim covert"}
def nkey(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = ALIAS.get(n, n)
    return re.sub(r"[^a-z]", "", n)

def main():
    raw = json.load(open(os.path.join(DATA, "_legends_raw.json")))
    req = urllib.request.Request(PLAYERS, headers={"User-Agent": "our-guys"})
    try: rows = list(csv.DictReader(io.StringIO(urllib.request.urlopen(req, timeout=120).read().decode("utf-8"))))
    except Exception: rows = list(csv.DictReader(open(sys.argv[1]))) if len(sys.argv) > 1 else []
    by = {}
    for p in rows:
        by.setdefault(nkey(p["display_name"]), []).append(p)
    ret = json.load(open(os.path.join(DATA, "retired.json"))); have = {r["id"] for r in ret}
    added, skipped, unmapped = [], [], set()
    for r in raw:
        if not r.get("ok"): skipped.append((r["name"], "no infobox")); continue
        b = r["box"]
        pt_text = re.sub(r"\{\{\s*NFL Year\s*\|\s*(\d{4})\s*\|\s*(\d{4})\s*\}\}", r"\1–\2", (b.get("pastteams") or b.get("teams") or ""))
        pt_text = re.sub(r"\{\{\s*NFL Year\s*\|\s*(\d{4})\s*\}\}", r"\1", pt_text)
        teams = []
        for line in plain(pt_text).split("\n"):
            m = re.match(r"\*?\s*(.+?)\s*\(([^)]*)\)", line.strip())
            ys = [int(y) for y in re.findall(r"\d{4}", m.group(2))] if m else []
            if m and ys and m.group(1).strip() in TEAM: teams.append([TEAM[m.group(1).strip()], min(ys), max(ys)])
        first = min((t[1] for t in teams), default=None); last = max((t[2] for t in teams), default=None)
        name = {'Ed "Too Tall" Jones': "Too Tall Jones"}.get(r["name"]) or re.sub(r'\s*"[^"]*"\s*', " ", r["name"]).strip()
        cands = [p for p in by.get(nkey(name), []) if p["last_season"] and int(p["last_season"]) <= 1998]
        if len(cands) > 1 and last: cands = [p for p in cands if abs(int(p["last_season"]) - last) <= 1]
        if len(cands) != 1: skipped.append((r["name"], f"{len(cands)} matches in player list, last season {last}")); continue
        p = cands[0]
        # the player list's seasons win; Wikipedia team lists are sometimes partial, and then they're dropped
        # the player list starts at 1974, so its rookie season is a floor for older careers; take the earlier of the two
        f2 = int(p["rookie_season"]) if p.get("rookie_season") else None
        l2 = int(p["last_season"])
        yrs = [int(y) for y in re.findall(r"\b(19[2-9]\d)\b", (b.get("pastteams") or b.get("teams") or "")) if int(y) <= l2]
        f2 = min([x for x in (f2, first, min(yrs) if yrs else None) if x] or [None])
        if teams and (last is None or last < l2 - 1 or (first and f2 and first > f2 + 1)): teams = []
        first, last = f2, l2
        if p["gsis_id"] in have: skipped.append((r["name"], "already in the app")); continue
        pos = POS.get(plain(b.get("position", "")).split("\n")[0].split("/")[0].strip().lower()) or POS.get((p.get("position") or "").lower()) or p.get("position_group") or p.get("position") or ""
        s = {}
        for k in [k for k in b if k.startswith("statlabel")]:
            lab = plain(b[k]).lower(); val = b.get("statvalue" + k[9:], "")
            if lab in ("td–int", "td-int", "touchdowns–interceptions"):
                m = re.findall(r"\d+", plain(val).replace(",", ""))
                if len(m) == 2: s["passing_tds"], s["passing_interceptions"] = int(m[0]), int(m[1])
                continue
            key = LABELS.get(lab)
            if not key: unmapped.add(lab); continue
            v = num(val)
            if v is not None: s[key] = v
        ht = None
        try: ht = int(b.get("height_ft", 0)) * 12 + int(re.sub(r"\D", "", b.get("height_in", "0")) or 0)
        except ValueError: pass
        wt = num(b.get("weight_lbs", "") or b.get("weight_lb", "") or "")
        rec = {"id": p["gsis_id"], "n": p["display_name"], "p": pos, "t": teams[-1][0] if teams else (p.get("latest_team") or "FA"), "f": first, "l": last, "x": 2, "w": 1}
        if p.get("jersey_number") not in (None, "", "0"): rec["j"] = p["jersey_number"]
        if NICK.get(p["display_name"]): rec["k"] = NICK[p["display_name"]]
        col = plain(b.get("college", "")).split("(")[0].strip() or p.get("college_name")
        if col: rec["c"] = col
        if b.get("draftyear") and b.get("draftround") and b.get("draftpick"):
            rec["d"] = f"{plain(b['draftyear'])}, round {plain(b['draftround'])}, pick {plain(b['draftpick'])}"
        if teams:
            rec["pt"] = [[t[0], f"{t[1]}-{str(t[2])[2:]}" if t[2] != t[1] else str(t[1])] for t in teams]
        if ht: rec["ht"] = ht
        if wt: rec["wt"] = wt
        if s: rec["s"] = s
        if plain(b.get("HOF", "")).strip(): rec["hof"] = 1      # infobox links his Hall of Fame page only if he's in
        rec["src"] = "https://en.wikipedia.org/wiki/" + r["title"].replace(" ", "_")
        ret.append(rec); have.add(rec["id"]); added.append(rec)
    ret.sort(key=lambda x: x["n"])
    json.dump(ret, open(os.path.join(DATA, "retired.json"), "w"), separators=(",", ":"), ensure_ascii=False)
    print(len(added), "added")
    for a in added: print("  +", a["n"], a["p"], a.get("f"), a.get("l"), a.get("s"))
    print("skipped:"); [print("  -", *x) for x in skipped]
    print("labels not used:", sorted(unmapped))

if __name__ == "__main__":
    main()
