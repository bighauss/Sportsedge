"""Read-only DFS canonical output receipt with strict original salary crosscheck.

This checks *local file structure*, SHA, lineup correctness, and distinct DK
CPT/FLEX identifiers. It cannot authenticate upstream DK CSVs, p_active,
ownership, contest payout, simulation convergence, or profitable EV.
Always PAPER / 0u. Never writes to accepted game inputs or lineups.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SALARY_COLUMNS = {"Name", "ID", "Roster Position", "Salary", "TeamAbbrev", "Status"}
PROJECTION_COLUMNS = {"player", "team", "flex_sal", "cpt_sal"}
INACTIVE_LABELS = {"IR", "OUT", "O", "INACTIVE", "D"}


def read_csv(path, required):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("required columns missing in " + path.name)
        rows = list(reader)
        if not rows:
            raise ValueError("empty " + path.name)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError("malformed CSV record in " + path.name)
        return rows


def integer(value, name, *, allow_zero=False):
    try:
        result = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid " + name) from exc
    if str(value).strip() != str(result) or result < (0 if allow_zero else 1):
        raise ValueError("invalid " + name)
    return result


def verify(tag, root=ROOT):
    root = Path(root).resolve()
    if not tag or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for c in tag):
        raise ValueError("bad tag")
    paths = {
        "engine": root / "showdown_mc.py",
        "config": root / "games" / (tag + ".json"),
        "salary": root / "data" / ("DKSalaries_" + tag + ".csv"),
        "projections": root / "out" / (tag + "_projections.csv"),
        "lineups": root / "out" / (tag + "_lineups.json"),
    }
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("missing required canonical file")
    cfg = json.loads(paths["config"].read_text(encoding="utf-8"))
    if cfg.get("tag") != tag or cfg.get("salary_file") != "data/DKSalaries_" + tag + ".csv":
        raise ValueError("config mismatch")
    projs = read_csv(paths["projections"], PROJECTION_COLUMNS)
    proj_by_name = {}
    for row in projs:
        name = row["player"].strip()
        team = row["team"].strip()
        if not name or not team or name in proj_by_name:
            raise ValueError("duplicate / missing projected player identity")
        integer(row["flex_sal"], "projected FLEX salary")
        integer(row["cpt_sal"], "projected CPT salary")
        proj_by_name[name] = row

    salary_rows = read_csv(paths["salary"], SALARY_COLUMNS)
    dk_rows = {}
    used_ids = set()
    for row in salary_rows:
        name, team, slot = (row["Name"].strip(), row["TeamAbbrev"].strip(),
                            row["Roster Position"].strip())
        if slot not in {"CPT", "FLEX"} or not name or not team:
            raise ValueError("invalid salary roster slot / identity")
        ident = integer(row["ID"], "DK salary ID")
        if ident in used_ids:
            raise ValueError("reused salary slot ID")
        used_ids.add(ident)
        integer(row["Salary"], "DK salary")
        key = (name, team, slot)
        if key in dk_rows:
            raise ValueError("duplicate DK player/slot entry")
        dk_rows[key] = row

    for name, p in proj_by_name.items():
        for slot, field in (("FLEX", "flex_sal"), ("CPT", "cpt_sal")):
            dk = dk_rows.get((name, p["team"].strip(), slot))
            if dk is None:
                raise ValueError("missing exact salary identity / slot")
            if integer(dk["Salary"], "DK salary") != integer(p[field], "projected salary"):
                raise ValueError("projected salary inconsistent with DK CSV")

    data = json.loads(paths["lineups"].read_text(encoding="utf-8"))
    summary = data.get("summary")
    if not isinstance(summary, dict) or summary.get("sims") != 20000:
        raise ValueError("unsupported simulation count claim")
    if "BLOCKED" not in str(summary.get("contest_ev", "")).upper():
        raise ValueError("contest EV must remain blocked")
    counts = {}
    unresolved_status = set()
    for key in ("top_by_mean", "top_by_opt_rate"):
        lineups = data.get(key)
        if not isinstance(lineups, list) or not lineups:
            raise ValueError("missing canonical lineup category")
        counts[key] = len(lineups)
        for lineup in lineups:
            players = [lineup["cpt"], *lineup["flex"]]
            if len(players) != 6 or len(set(players)) != 6 or any(p not in proj_by_name for p in players):
                raise ValueError("invalid DFS lineup identities")
            cost = 0
            for idx, name in enumerate(players):
                slot = "CPT" if idx == 0 else "FLEX"
                projected = proj_by_name[name]
                dk = dk_rows[(name, projected["team"].strip(), slot)]
                status = dk["Status"].strip().upper()
                if status in INACTIVE_LABELS:
                    raise ValueError("lineup contains marked inactive player")
                if status:
                    unresolved_status.add(name + ":" + status)
                cost += integer(dk["Salary"], "DK lineup salary")
            if cost != integer(lineup["salary"], "lineup salary") or cost > 50000:
                raise ValueError("invalid actual DK lineup salary")
    return {
        "tag": tag, "status": "PAPER_NO_VERIFIED_EV", "simulations_claimed": 20000,
        "players": len(proj_by_name), "lineups": counts,
        "questionable_or_nonempty_status_unverified": sorted(unresolved_status),
        "source_authentication_independent": False,
        "ownership_verified": False,
        "injury_status_independent_receipt": False,
        "official_stake_u": 0,
        "sha256": {k: hashlib.sha256(path.read_bytes()).hexdigest() for k, path in paths.items()},
        "independently_reproduced": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    args = parser.parse_args()
    print(json.dumps(verify(args.tag), indent=2, sort_keys=True))
