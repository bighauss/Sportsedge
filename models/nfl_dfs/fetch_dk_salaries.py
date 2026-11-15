"""Pull DraftKings slate salaries (DKSalaries.csv-style columns) from DK's public JSON
endpoints. Stdlib only. Meant to run in GitHub Actions (free on public repos).
Output: models/nfl_dfs/data/dk_auto/. Endpoints are unofficial; on failure it exits
non-zero and writes nothing made up.

python models/nfl_dfs/fetch_dk_salaries.py [NFL|CFB|NBA|CBB|NHL]
"""
import csv, json, os, sys, urllib.request

LOBBY = "https://www.draftkings.com/lobby/getcontests?sport={sport}"
DRAFTABLES = "https://api.draftkings.com/draftgroups/v1/draftgroups/{dg}/draftables"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dk_auto")

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SportsEdge-research"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def draft_groups(sport):
    lobby = get(LOBBY.format(sport=sport))
    return [dict(id=g["DraftGroupId"], start=g.get("StartDateEst", ""), games=g.get("GameCount"),
                 suffix=(g.get("ContestStartTimeSuffix") or "").strip()) for g in lobby.get("DraftGroups", [])]

def to_rows(js):
    comp = {c["competitionId"]: c for c in js.get("competitions", [])}
    rows = []
    for d in js.get("draftables", []):
        c = comp.get(d.get("competition", {}).get("competitionId"), {})
        name = d.get("displayName", "")
        rows.append({"Position": d.get("position", ""), "Name + ID": f"{name} ({d.get('draftableId')})",
                     "Name": name, "ID": d.get("draftableId"), "Roster Position": d.get("rosterSlotId"),
                     "Salary": d.get("salary"), "Game Info": c.get("name", ""),
                     "TeamAbbrev": d.get("teamAbbreviation", ""),
                     "AvgPointsPerGame": next((a.get("value") for a in d.get("draftStatAttributes", []) if a.get("id") == 90), ""),
                     "Status": "" if d.get("status") in (None, "None") else d.get("status")})
    return rows

def main():
    sport = sys.argv[1] if len(sys.argv) > 1 else "NFL"
    os.makedirs(OUT, exist_ok=True)
    groups = draft_groups(sport)
    if not groups:
        sys.exit("no draft groups returned")
    index = []
    for g in groups:
        try:
            rows = to_rows(get(DRAFTABLES.format(dg=g["id"])))
        except Exception as e:
            index.append(dict(g, error=str(e))); continue
        if not rows: continue
        fn = f"DKSalaries_{sport}_{g['id']}.csv"
        with open(os.path.join(OUT, fn), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        index.append(dict(g, file=fn, players=len(rows)))
    json.dump(index, open(os.path.join(OUT, f"index_{sport}.json"), "w"), indent=1)
    print(json.dumps(index, indent=1))

if __name__ == "__main__":
    main()
