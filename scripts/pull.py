"""Builds data/*.json from free nflverse feeds. Run nightly by GitHub Actions.
Outputs: players.json (bio + past teams), stats.json (season, last game, advanced), meta.json, career.json (career totals, active players)
"""
import csv, io, json, os, sys, urllib.request, datetime as dt
from collections import defaultdict

REL = "https://github.com/nflverse/nflverse-data/releases/download/"
GAMES = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

def fetch(url, required=True):
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return list(csv.DictReader(io.StringIO(r.read().decode("utf-8", "replace"))))
    except Exception as e:
        if required: raise
        print("skip", url, e); return []

def n(v):
    try: return float(v)
    except: return 0.0

def pos_of(p):
    pos, ngs = p["position"], p.get("ngs_position", "")
    if pos == "QB": return "QB"
    if pos in ("RB", "FB"): return "RB"
    if pos == "WR": return "WR"
    if pos == "TE": return "TE"
    if pos in ("OT", "G", "C", "OL", "T"): return "OL"
    if pos in ("K", "P", "LS"): return pos
    if ngs == "EDGE": return "EDGE"
    if ngs == "INTERIOR_LINE" or pos in ("DT", "NT", "DL"): return "DL"
    if pos == "DE": return "EDGE"
    if ngs in ("CB", "SLOT_CB") or pos == "CB": return "CB"
    if ngs in ("SAFETY", "HIGH_SAFETY") or pos in ("SAF", "S", "SS", "FS"): return "S"
    if pos == "DB": return "CB"
    if pos in ("LB", "OLB", "ILB", "MLB"): return "LB"
    return pos

def season_now():
    today = dt.date.today()
    return today.year if today.month >= 8 else today.year - 1

def runs(d):
    out, cur = [], None
    for yr in sorted(d):
        t = d[yr]
        if cur and cur[0] == t and cur[2] == yr - 1: cur[2] = yr
        else:
            cur = [t, yr, yr]; out.append(cur)
    return [[t, str(a) if a == b else f"{a}-{str(b)[2:]}"] for t, a, b in out]

# ---- career totals (shared with build_history.py) ----
CAREER_KEYS = ["completions","attempts","passing_yards","passing_tds","passing_interceptions","carries","rushing_yards","rushing_tds",
               "targets","receptions","receiving_yards","receiving_tds","def_sacks","def_tackles_for_loss","def_qb_hits","def_fumbles_forced",
               "def_interceptions","def_pass_defended","fg_made","fg_att","pat_made","pat_att","pt_att","pt_yards","pt_inside_20"]
TEAM_ALIAS = {"OAK":"LV","SD":"LAC","STL":"LA","RAM":"LA","RAI":"LV","PHO":"ARI","SL":"LA","JAC":"JAX","HST":"HOU","BLT":"BAL","CLV":"CLE","ARZ":"ARI","GNB":"GB","KAN":"KC","NWE":"NE","NOR":"NO","SFO":"SF","TAM":"TB","SDG":"LAC","LAR":"LA"}

def norm_team(t, yr=None):
    if t == "HOU" and yr and yr <= 1996: return "TEN"   # Oilers became the Titans
    return TEAM_ALIAS.get(t, t)

def add_season(tot, r):
    tot["gp"] += n(r.get("games"))
    for k in CAREER_KEYS: tot[k] += n(r.get(k))
    tot["tackles"] += n(r.get("def_tackles_solo")) + n(r.get("def_tackles_with_assist"))
    tot["fg_long"] = max(tot["fg_long"], n(r.get("fg_long")))
    tot["pt_long"] = max(tot["pt_long"], n(r.get("pt_long")))

def finish_career(tot):
    out = {}
    for k, v in tot.items():
        if v: out[k] = int(v) if float(v).is_integer() else round(v, 1)
    return out

def _f(x):
    x = n(x); return f"{int(x):,}" if float(x).is_integer() else f"{x:,.1f}"

def best_season(pos, rows):
    """Pick the signature season by the position's headline stat. Returns [year, text] or None."""
    key = {"QB":"passing_yards","RB":"rushing_yards","WR":"receiving_yards","TE":"receiving_yards","EDGE":"def_sacks","DL":"def_sacks",
           "CB":"def_interceptions","S":"def_interceptions","DB":"def_interceptions","K":"fg_made","P":"pt_yards"}.get(pos)
    if pos == "LB": score = lambda r: n(r.get("def_tackles_solo")) + n(r.get("def_tackles_with_assist"))
    elif key: score = lambda r: n(r.get(key))
    else: return None
    rows = [r for r in rows if score(r) > 0]
    if not rows: return None
    r = max(rows, key=lambda r: (score(r), n(r.get("season"))))
    tk = n(r.get("def_tackles_solo")) + n(r.get("def_tackles_with_assist"))
    if pos == "QB": t = f"{_f(r['passing_yards'])} pass yards, {_f(r['passing_tds'])} TD, {_f(r['passing_interceptions'])} INT"
    elif pos == "RB": t = f"{_f(r['rushing_yards'])} rush yards, {_f(r['rushing_tds'])} TD"
    elif pos in ("WR", "TE"): t = f"{_f(r['receptions'])} catches, {_f(r['receiving_yards'])} yards, {_f(r['receiving_tds'])} TD"
    elif pos in ("EDGE", "DL"): t = f"{_f(r['def_sacks'])} sacks, {_f(tk)} tackles"
    elif pos == "LB": t = f"{_f(tk)} tackles, {_f(r['def_sacks'])} sacks"
    elif pos in ("CB", "S", "DB"): t = f"{_f(r['def_interceptions'])} INT, {_f(tk)} tackles"
    elif pos == "K": t = f"{_f(r['fg_made'])} of {_f(r['fg_att'])} field goals"
    else: t = f"{_f(r['pt_att'])} punts, {n(r['pt_yards'])/max(1,n(r['pt_att'])):.1f} average"
    return [int(n(r["season"])), t]

def build_career(active, season):
    """Career totals for active players: data/career.json = {id: {s: totals, b: [year, text], f: first season in data}}"""
    pos = {p["gsis_id"]: pos_of(p) for p in active}
    tot = defaultdict(lambda: defaultdict(float)); rows = defaultdict(list)
    for yr in range(1999, season + 1):
        for r in fetch(REL + f"stats_player/stats_player_reg_{yr}.csv", required=False):
            pid = r.get("player_id")
            if pid in pos:
                add_season(tot[pid], r); rows[pid].append(r)
    out = {}
    for pid, t in tot.items():
        rec = {"s": finish_career(t)}
        b = best_season(pos[pid], rows[pid])
        if b: rec["b"] = b
        out[pid] = rec
    json.dump(out, open(os.path.join(OUT, "career.json"), "w"), separators=(",", ":"))
    print(len(out), "career lines")

def main():
    season = int(sys.argv[1]) if len(sys.argv) > 1 else season_now()
    allgames = fetch(GAMES)
    games = [g for g in allgames if g["season"] == str(season)]
    if not any(g["away_score"] for g in games):
        season -= 1
        games = [g for g in allgames if g["season"] == str(season)]
    played = {g["game_id"]: g for g in games if g["away_score"] != ""}
    last_week = max((int(g["week"]) for g in played.values()), default=0)
    print("season", season, "through week", last_week)

    weekly = [w for w in fetch(REL + f"stats_player/stats_player_week_{season}.csv") if w["season_type"] == "REG"]
    adv = fetch(REL + f"pfr_advstats/advstats_week_def_{season}.csv", required=False)
    players = fetch(REL + "players/players.csv")
    active = [p for p in players if p["status"] == "ACT" and p["last_season"] == str(season)]
    ids = {p["gsis_id"] for p in active}
    pfr_to_id = {p["pfr_id"]: p["gsis_id"] for p in active if p["pfr_id"]}

    rookie_min = min((int(p["rookie_season"]) for p in active if p["rookie_season"]), default=season)
    hist = defaultdict(dict)
    for yr in range(max(rookie_min, 2000), season + 1):
        for r in fetch(REL + f"rosters/roster_{yr}.csv", required=False):
            if r["gsis_id"] in ids and r.get("team"):
                hist[r["gsis_id"]][yr] = r["team"]

    today = dt.date.today()
    out_players = []
    for p in active:
        age = ""
        if p["birth_date"]:
            b = dt.date.fromisoformat(p["birth_date"])
            age = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
        drafted = "Undrafted" + (f", {p['rookie_season']}" if p["rookie_season"] else "")
        if p["draft_year"]:
            drafted = f"{p['draft_year']}, round {p['draft_round']}, pick {p['draft_pick']}"
        out_players.append({
            "id": p["gsis_id"], "name": p["display_name"], "pos": pos_of(p), "team": p["latest_team"],
            "num": p["jersey_number"], "headshot": p["headshot"], "college": p["college_name"],
            "age": age, "drafted": drafted,
            "past": runs(hist.get(p["gsis_id"], {})) or [[p["latest_team"], str(season)]],
        })

    skip = {"player_id","player_name","player_display_name","position","position_group","headshot_url","season","week","season_type","game_id","team","opponent_team"}
    tot = defaultdict(lambda: defaultdict(float)); last = {}; gp = defaultdict(int); num_cols = None
    for w in weekly:
        pid = w["player_id"]
        if pid not in ids: continue
        if num_cols is None:
            num_cols = [k for k in w if k not in skip and not k.endswith("_list")]
        gp[pid] += 1
        for k in num_cols: tot[pid][k] += n(w[k])
        wk = int(w["week"])
        if pid not in last or wk > last[pid]["wk"]:
            g = played.get(w["game_id"], {})
            home = g.get("home_team") == w["team"]
            us, them = (g.get("home_score"), g.get("away_score")) if home else (g.get("away_score"), g.get("home_score"))
            res = ""
            if us not in (None, ""):
                us, them = int(float(us)), int(float(them))
                res = ("won" if us > them else "lost" if us < them else "tied") + f" {us}-{them}"
            last[pid] = {"wk": wk, "opp": w["opponent_team"], "home": home, "res": res,
                         "line": {k: round(n(w[k]), 1) for k in num_cols if n(w[k])}}

    adv_tot = defaultdict(lambda: defaultdict(float)); adv_wk = defaultdict(int)
    for a in adv:
        pid = pfr_to_id.get(a["pfr_player_id"])
        if not pid or a["game_type"] != "REG": continue
        adv_wk[pid] = max(adv_wk[pid], int(a["week"]))
        for k in ("def_targets","def_completions_allowed","def_yards_allowed","def_times_blitzed","def_times_hurried","def_times_hitqb","def_pressures","def_missed_tackles"):
            adv_tot[pid][k] += n(a[k])
        adv_tot[pid]["_rt"] += n(a["def_passer_rating_allowed"]) * n(a["def_targets"])

    def rd(x, d=1): return round(x, d) if d else int(round(x))
    stats = {}
    for pid in tot:
        t = tot[pid]; s = {"gp": gp[pid]}
        att = t["attempts"]
        if att:
            a = max(0, min(2.375, (t["completions"]/att - .3)*5)); b = max(0, min(2.375, (t["passing_yards"]/att - 3)*.25))
            c = max(0, min(2.375, t["passing_tds"]/att*20)); d = max(0, min(2.375, 2.375 - t["passing_interceptions"]/att*25))
            s["rating"] = rd((a+b+c+d)/6*100)
        s.update({k: rd(v) for k, v in t.items() if v})
        s["ypc"] = rd(t["rushing_yards"]/t["carries"]) if t["carries"] else 0
        s["ypr"] = rd(t["receiving_yards"]/t["receptions"]) if t["receptions"] else 0
        s["tackles"] = rd(t["def_tackles_solo"] + t["def_tackles_with_assist"], 0)
        s["last"] = last.get(pid)
        if pid in adv_tot:
            v = adv_tot[pid]; tg = v["def_targets"]
            s["adv"] = {"thru": adv_wk[pid], "targets": rd(tg,0), "comp_pct": rd(v["def_completions_allowed"]/tg*100) if tg else 0,
                        "yds_allowed": rd(v["def_yards_allowed"],0), "rating_allowed": rd(v["_rt"]/tg) if tg else 0,
                        "pressures": rd(v["def_pressures"],0), "hits": rd(v["def_times_hitqb"],0), "hurries": rd(v["def_times_hurried"],0),
                        "blitzes": rd(v["def_times_blitzed"],0), "missed": rd(v["def_missed_tackles"],0)}
        stats[pid] = s

    os.makedirs(OUT, exist_ok=True)
    json.dump(out_players, open(os.path.join(OUT, "players.json"), "w"), separators=(",", ":"))
    json.dump(stats, open(os.path.join(OUT, "stats.json"), "w"), separators=(",", ":"))
    json.dump({"season": season, "week": last_week, "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
              open(os.path.join(OUT, "meta.json"), "w"))
    print(len(out_players), "players,", len(stats), "with stats")
    try:
        build_career(active, season)
    except Exception as e:   # never let the career file break the nightly stats
        print("career skipped:", e)
    try:
        import colts; colts.main(False)
    except Exception as e:   # the Colts game-day file is optional too
        print("colts skipped:", e)

if __name__ == "__main__":
    main()
