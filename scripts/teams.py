"""Team season totals: data/teams.json (record, points, yards for and against, turnovers, sacks).

Called by the nightly pull. Yards come from nflverse team-week stats; record and points from the games list.
The app turns these into per-game numbers and league ranks.
"""
import json, os
from collections import defaultdict
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "teams.json")

def n(v):
    try: return float(v)
    except (TypeError, ValueError): return 0.0

def build(games, teamweek):
    """games: rows of nflverse games.csv for the season. teamweek: rows of stats_team_week for the season."""
    T = defaultdict(lambda: defaultdict(float))
    for g in games:
        if g.get("game_type", "REG") != "REG" or g.get("away_score") in ("", None): continue
        hs, as_ = n(g["home_score"]), n(g["away_score"])
        for me, them, a, b in ((g["home_team"], g["away_team"], hs, as_), (g["away_team"], g["home_team"], as_, hs)):
            t = T[me]; t["g"] += 1; t["pf"] += a; t["pa"] += b
            t["w" if a > b else "l" if a < b else "t"] += 1
    for r in teamweek:
        if r.get("season_type") != "REG": continue
        me, opp = r["team"], r["opponent_team"]
        py = n(r.get("passing_yards")) - abs(n(r.get("sack_yards_lost")))     # net passing, the way team rankings count it
        ry = n(r.get("rushing_yards"))
        give = n(r.get("passing_interceptions")) + (n(r["fumbles_lost_total"]) if r.get("fumbles_lost_total") not in ("", None) else
                                                    n(r.get("sack_fumbles_lost")) + n(r.get("rushing_fumbles_lost")) + n(r.get("receiving_fumbles_lost")))
        sk = n(r.get("sacks_suffered"))
        t, o = T[me], T[opp]
        t["sg"] += 1; t["py"] += py; t["ry"] += ry; t["give"] += give; t["ska"] += sk
        o["pya"] += py; o["rya"] += ry; o["take"] += give; o["sk"] += sk
    out = {k: {a: (round(v, 1) if v % 1 else int(v)) for a, v in t.items()} for k, t in T.items()}
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    print("teams:", len(out), "teams")
    return out
