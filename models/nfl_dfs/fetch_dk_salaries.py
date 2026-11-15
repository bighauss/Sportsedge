"""Unofficial DK public-lobby salary discovery, **not** a DFS projection engine.

Canonical Showdown projections must still use showdown_mc.py + games/<GAME>.json
and the OWNER'S salary_file CSV. This fetcher only creates quarantined review
snapshots in data/dk_auto; it never edits that canonical game or salaries file.

Roster-slot IDs are not stable CPT/FLEX labels. A numeric ID without an
explicit label in the very same public response is rejected, never guessed.

Usage: python models/nfl_dfs/fetch_dk_salaries.py NFL
"""
from __future__ import annotations

import csv
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
LOBBY = "https://www.draftkings.com/lobby/getcontests?sport={sport}"
DRAFTABLES = "https://api.draftkings.com/draftgroups/v1/draftgroups/{dg}/draftables"
OUT = HERE / "data" / "dk_auto"
SPORTS = frozenset(("NFL",))  # showdown-specific; no generic NBA/CBB DFS roster-slot inference
FIELDS = ("Position", "Name + ID", "Name", "ID", "Roster Position", "Salary",
          "Game Info", "TeamAbbrev", "AvgPointsPerGame", "Status")
POSITIONS = frozenset(("QB", "RB", "WR", "TE", "K", "DST"))
DK_SLOTS = frozenset(("CPT", "FLEX"))
SAFE_ID = re.compile(r"[1-9][0-9]{0,14}\Z")


def get(url):
    """Read the two allowlisted public endpoints; DK may block or change them."""
    valid_lobby = url in {LOBBY.format(sport=s) for s in SPORTS}
    valid_dg = re.fullmatch(r"https://api\.draftkings\.com/draftgroups/v1/draftgroups/([1-9][0-9]{0,14})/draftables", url)
    if not valid_lobby and not valid_dg:
        raise ValueError("UNREGISTERED_DK_PUBLIC_ENDPOINT")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 SportsEdge-research"})
    with urlopen(req, timeout=30) as response:
        raw = response.read(10_000_001)
    if not raw or len(raw) > 10_000_000:
        raise ValueError("DK_RESPONSE_EMPTY_OR_OVERSIZE")
    return json.loads(raw.decode("utf-8"))


def draft_groups(sport):
    if sport not in SPORTS:
        raise ValueError("UNSUPPORTED_DK_SPORT")
    lobby = get(LOBBY.format(sport=sport))
    if not isinstance(lobby, dict) or not isinstance(lobby.get("DraftGroups"), list):
        raise ValueError("DK_LOBBY_SCHEMA_UNKNOWN")
    groups = []
    seen = set()
    for group in lobby["DraftGroups"]:
        if not isinstance(group, dict):
            raise ValueError("DK_LOBBY_GROUP_INVALID")
        group_id = str(group.get("DraftGroupId", ""))
        if not SAFE_ID.fullmatch(group_id) or group_id in seen:
            raise ValueError("DK_DRAFT_GROUP_ID_MISSING_OR_DUPLICATE")
        seen.add(group_id)
        groups.append(dict(id=group_id, start=group.get("StartDateEst", ""),
                           games=group.get("GameCount"),
                           suffix=(group.get("ContestStartTimeSuffix") or "").strip()))
    return groups


def _slot_mapping(js):
    """Never assign numeric roster-slot IDs based on unverified conventions."""
    mapping = {}
    slots = js.get("rosterSlots", [])
    if not isinstance(slots, list):
        raise ValueError("DK_ROSTER_SLOT_METADATA_INVALID")
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("DK_ROSTER_SLOT_METADATA_INVALID")
        sid = slot.get("rosterSlotId", slot.get("id"))
        label = slot.get("name", slot.get("label", slot.get("rosterSlotName")))
        if isinstance(sid, bool) or not isinstance(sid, (int, str)) or label not in DK_SLOTS:
            raise ValueError("DK_ROSTER_SLOT_METADATA_UNVERIFIED")
        key = str(sid)
        if key in mapping and mapping[key] != label:
            raise ValueError("DK_ROSTER_SLOT_METADATA_CONFLICT")
        mapping[key] = label
    return mapping


def _label(d, slots):
    for field in ("rosterPosition", "rosterSlotName"):
        label = d.get(field)
        if isinstance(label, str) and label.upper() in DK_SLOTS:
            return label.upper()
    raw = d.get("rosterSlotId")
    if isinstance(raw, str) and raw.upper() in DK_SLOTS:
        return raw.upper()
    label = slots.get(str(raw))
    if label in DK_SLOTS:
        return label
    raise ValueError("DK_SHOWDOWN_CPT_FLEX_SLOT_NOT_VERIFIED")


def to_rows(js):
    """Normalize one unverified public draftgroup; only sound Showdown pairs pass.

    Never use DK AvgPointsPerGame for model projections. Leave that CSV field
    blank; role, scoring projections and p_active come only from versioned game JSON.
    """
    if not isinstance(js, dict) or not isinstance(js.get("draftables"), list):
        raise ValueError("DK_DRAFTABLES_SCHEMA_INVALID")
    comp = js.get("competitions", [])
    if not isinstance(comp, list):
        raise ValueError("DK_COMPETITIONS_SCHEMA_INVALID")
    competitions = {}
    for c in comp:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str):
            raise ValueError("DK_COMPETITION_INVALID")
        key = str(c.get("competitionId", ""))
        if not key or key in competitions:
            raise ValueError("DK_COMPETITION_DUPLICATED_OR_MISSING")
        competitions[key] = c["name"]
    slots = _slot_mapping(js)
    rows, by_player, unique_ids = [], {}, set()
    for d in js["draftables"]:
        if not isinstance(d, dict):
            raise ValueError("DK_DRAFTABLE_INVALID")
        name = d.get("displayName")
        team = d.get("teamAbbreviation")
        pos = d.get("position")
        number = d.get("draftableId")
        salary = d.get("salary")
        if (not isinstance(name, str) or not name.strip() or not isinstance(team, str)
                or not team.strip() or pos not in POSITIONS or isinstance(number, bool)
                or not SAFE_ID.fullmatch(str(number)) or isinstance(salary, bool)
                or not isinstance(salary, int) or not 100 <= salary <= 100000):
            raise ValueError("DK_DRAFTABLE_ID_TEAM_POS_OR_SALARY_INVALID")
        game = d.get("competition")
        comp_id = str(game.get("competitionId")) if isinstance(game, dict) else ""
        if comp_id not in competitions:
            raise ValueError("DK_DRAFTABLE_COMPETITION_ID_UNVERIFIED")
        slot = _label(d, slots)
        name = name.strip()
        if str(number) in unique_ids:
            raise ValueError("DK_DRAFTABLE_ID_REUSED")
        unique_ids.add(str(number))
        key = (name.casefold(), team.upper(), pos, comp_id)
        player = by_player.setdefault(key, {})
        if slot in player:
            raise ValueError("DK_DUPLICATE_PLAYER_ROSTER_SLOT")
        player[slot] = salary
        status = d.get("status")
        if status is None:
            status = ""
        if not isinstance(status, str):
            raise ValueError("DK_DRAFTABLE_STATUS_INVALID")
        rows.append({"Position": pos, "Name + ID": f"{name} ({number})", "Name": name,
                     "ID": str(number), "Roster Position": slot, "Salary": salary,
                     "Game Info": competitions[comp_id], "TeamAbbrev": team.upper(),
                     "AvgPointsPerGame": "", "Status": status})
    if not rows:
        raise ValueError("DK_SHOWDOWN_DRAFTGROUP_EMPTY")
    for positions in by_player.values():
        if set(positions) != DK_SLOTS:
            raise ValueError("DK_INCOMPLETE_CPT_FLEX_PAIR")
        if 2 * positions["CPT"] != 3 * positions["FLEX"]:
            raise ValueError("DK_CPT_SALARY_NOT_1P5_FLEX")
    # Same Name across distinct teams or games cannot be keyed by showdown_mc.
    by_name = {}
    for name, team, pos, competition in by_player:
        ident = (team, pos, competition)
        if name in by_name and by_name[name] != ident:
            raise ValueError("DK_AMBIGUOUS_SAME_NAME_PLAYER")
        by_name[name] = ident
    rows.sort(key=lambda r: (r["Name"].casefold(), r["Roster Position"]))
    return rows


def verify_owner_game(game_json, salary_csv):
    """Read-only check of EXACT owner CSV against one versioned canonical game.

    Does not change salary file or projections, and never consults DK avg FP.
    """
    with open(game_json, encoding="utf-8") as f:
        game = json.load(f)
    with open(salary_csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, restkey=None, restval=None)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("OWNER_SALARY_HEADERS_MISSING")
        rows = list(reader)
    if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("OWNER_SALARY_MALFORMED")
    tag_parts = game.get("tag", "").split("_")
    if len(tag_parts) < 3 or not tag_parts[0] or not tag_parts[1]:
        raise ValueError("OWNER_GAME_TAG_MISSING")
    expected_matchup = f"{tag_parts[0]}@{tag_parts[1]} "
    if any(not row["Game Info"].startswith(expected_matchup) for row in rows):
        raise ValueError("OWNER_SALARY_MATCHUP_NOT_CANONICAL_GAME")
    seen, people, idseen = set(), {}, set()
    for row in rows:
        name = row["Name"].strip();slot = row["Roster Position"].strip()
        team = row["TeamAbbrev"].strip();pos = row["Position"].strip()
        if not name or slot not in DK_SLOTS or not team or not pos:
            raise ValueError("OWNER_SALARY_IDENTITY_MISSING")
        key = (name, slot)
        if key in seen or row["ID"] in idseen:
            raise ValueError("OWNER_SALARY_DUPLICATE_PLAYER_OR_ID")
        seen.add(key);idseen.add(row["ID"])
        if not str(row["Salary"]).isdigit() or int(row["Salary"]) <= 0:
            raise ValueError("OWNER_SALARY_NUMERIC_INVALID")
        p = people.setdefault(name, {"team":team,"pos":pos,"slots":{}})
        if p["team"] != team or p["pos"] != pos:
            raise ValueError("OWNER_SALARY_TEAM_POS_INCONSISTENT")
        p["slots"][slot] = int(row["Salary"])
    for name, config in game["players"].items():
        if name not in people:
            raise ValueError("OWNER_SALARY_CONFIG_PLAYER_MISSING:"+name)
        p = people[name]
        if p["team"] != config["team"] or p["pos"] != config["pos"]:
            raise ValueError("OWNER_SALARY_CONFIG_TEAM_POS_MISMATCH:"+name)
        if set(p["slots"]) != DK_SLOTS or 2*p["slots"]["CPT"] != 3*p["slots"]["FLEX"]:
            raise ValueError("OWNER_SALARY_CONFIG_CPT_FLEX_INCOMPLETE:"+name)
        active = config.get("p_active")
        if isinstance(active, bool) or not isinstance(active, (int,float)) or not 0 <= active <= 1:
            raise ValueError("OWNER_GAME_ACTIVE_PROB_INVALID:"+name)
    return {"status":"OWNER_CSV_STRUCTURE_VERIFIED_RESEARCH_ONLY",
            "engine":"models/nfl_dfs/showdown_mc.py", "seed":7,
            "player_count":len(game["players"]),"owner_salary_rows":len(rows),
            "owner_salary_sha256":"sha256:"+sha256(Path(salary_csv).read_bytes()).hexdigest(),
            "game_sha256":"sha256:"+sha256(Path(game_json).read_bytes()).hexdigest(),
            "config_tag":game["tag"],"DK_avg_fp_used":False,
            "owner_csv_modified":False,"official_contest_ev":None,
            "note":"Structure only; no unvalidated ownership, outcomes, or independent publication proof."}


def _write_provisional(path, rows):
    """Exclusive-create: never silently replace a snapshot or owner CSV."""
    with path.open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader();writer.writerows(rows)
    return "sha256:"+sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1 or (argv and argv[0] not in SPORTS):
        raise SystemExit("Usage: python models/nfl_dfs/fetch_dk_salaries.py NFL")
    sport = argv[0] if argv else "NFL"
    groups = draft_groups(sport)
    if not groups:
        raise SystemExit("No DK draft groups returned; owner file remains authoritative")
    # Discovery files only; never update the salary_file referenced in games/*.json.
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for g in groups:
        try:
            rows = to_rows(get(DRAFTABLES.format(dg=g["id"])))
            name = f"DKSalaries_{sport}_{g['id']}.csv"
            digest = _write_provisional(OUT / name, rows)
            index.append(dict(g, file=name, players=len(rows)//2, csv_sha256=digest,
                              status="QUARANTINED_UNOFFICIAL_DISCOVERY_ONLY"))
        except (ValueError, KeyError, TypeError, OSError) as e:
            index.append(dict(g, status="BLOCKED_NO_AUTHORITATIVE_SALARY_CHANGE",
                              reason=type(e).__name__+":"+str(e)))
    # Index is stdout only. Do not overwrite previous index or owner CSV.
    print(json.dumps({"sport":sport,"rulebook":"docs/handoffs/DFS_SAME_PAGE.md",
                      "canonical_salary_file_unchanged":True,"results":index},indent=2))
    if not any(x.get("file") for x in index):
        raise SystemExit("No unambiguous Showdown CPT/FLEX draftgroup; owner CSV unchanged")


if __name__ == "__main__":
    main()
