"""Builds data/retired.json: every retired player since 1999 plus hand-verified legends.

Run by hand when a season ends (python3 scripts/build_history.py). Not part of the nightly job.
Sources: nflverse season stats 1999+, nflverse rosters 1980+, scripts/legends.json (verified full-career
totals for stars whose careers began before 1999).
"""
import csv, io, json, os, sys, urllib.request, datetime as dt
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pull import fetch, pos_of, runs, REL, OUT, season_now, CAREER_KEYS, add_season, finish_career, best_season, norm_team

HERE = os.path.dirname(os.path.abspath(__file__))
HEAD_PREFIX = "https://static.www.nfl.com/image/"

def main():
    season = season_now()
    players = fetch(REL + "players/players.csv")
    legends = {x["id"]: x for x in json.load(open(os.path.join(HERE, "legends.json")))}
    active = {p["gsis_id"] for p in players if p["status"] == "ACT" and p["last_season"] == str(season)}

    career = defaultdict(lambda: defaultdict(float)); seasons = defaultdict(list); teams = defaultdict(dict)
    for yr in range(1999, season + 1):
        for r in fetch(REL + f"stats_player/stats_player_reg_{yr}.csv", required=False):
            pid = r.get("player_id")
            if not pid or pid in active: continue
            add_season(career[pid], r); seasons[pid].append(r)
            if r.get("recent_team"): teams[pid][yr] = norm_team(r["recent_team"], yr)
    for yr in range(1980, season + 1):
        for r in fetch(REL + f"rosters/roster_{yr}.csv", required=False):
            pid = r.get("gsis_id")
            if pid and pid not in active and r.get("team") and yr not in teams[pid]:
                teams[pid][yr] = norm_team(r["team"], yr)

    out = []
    for p in players:
        pid = p["gsis_id"]
        if not pid or pid in active: continue
        leg = legends.get(pid)
        last = int(p["last_season"]) if p["last_season"] else 0
        if not leg and last < 1999: continue
        rookie = int(p["rookie_season"]) if p["rookie_season"] else 0
        pos = leg["pos"] if leg else pos_of(p)
        if pos == "CB" and p["position"] == "DB": pos = "DB"
        rec = {"id": pid, "n": p["display_name"], "p": pos, "t": norm_team(p["latest_team"], last), "f": rookie or None, "l": last or None}
        if p["jersey_number"]: rec["j"] = p["jersey_number"]
        if p["headshot"].startswith(HEAD_PREFIX): rec["h"] = p["headshot"][len(HEAD_PREFIX):]
        if p["college_name"]: rec["c"] = p["college_name"]
        if p["draft_year"]: rec["d"] = f"{p['draft_year']}, round {p['draft_round']}, pick {p['draft_pick']}"
        elif rookie: rec["d"] = f"Undrafted, {rookie}"
        pt = runs(teams.get(pid, {}))
        if pt: rec["pt"] = pt
        if leg:
            rec["s"] = leg["career"]; rec["b"] = [leg["best"]["year"], leg["best"]["text"]]; rec["x"] = 2
            rec["f"] = leg.get("first", rec["f"]); rec["l"] = leg.get("last", rec["l"])
        elif pid in career:
            rec["s"] = finish_career(career[pid])
            b = best_season(pos, seasons[pid])
            if b: rec["b"] = b
            if rookie and rookie < 1999: rec["x"] = 1
        out.append(rec)

    out.sort(key=lambda r: r["n"])
    json.dump(out, open(os.path.join(OUT, "retired.json"), "w"), separators=(",", ":"), ensure_ascii=False)
    print(len(out), "retired players;", sum(1 for r in out if r.get("x") == 2), "verified legends;", sum(1 for r in out if "s" in r), "with stats")

if __name__ == "__main__":
    main()
