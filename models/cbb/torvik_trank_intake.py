"""Strict Barttorvik T-Rank team-table intake. PAPER / research only.

Fails closed: malformed rows are quarantined with a reason, never guessed. Input is page TEXT, not
provider-original bytes: callers must record capture UTC; provenance is marked unauthenticated.
"""
from __future__ import annotations
import hashlib, math, re
from datetime import datetime

NCELL = 24
COLS = ("rk","team","conf","g","rec","adjoe","adjde","barthag","efg","efgd","tor","tord","orb","drb",
        "ftr","ftrd","p2","p2d","p3","p3d","p3r","p3rd","adjt","wab")
_SUFFIX = re.compile(r"\s+(?:vs\.|\(H\)|\(A\)|\(N\))\s+\d+\s+.+$")
_HEADER = re.compile(r"D-I Avg:\|([\d.]+)\|[\d.]+\|[\d.]+\|Eff\.\s*FG%\s*([\d.]+)\|.*?Turnover%\s*([\d.]+)\|.*?Rebound%\s*([\d.]+)\|.*?FT Rate\s*([\d.]+)\|.*?3-Pt %\s*([\d.]+)\|.*?3P Rate\s*([\d.]+)\|.*?\|([\d.]+)\|")

# Verified pairs only (keys used in research/cbb_web_fallback/run.py on claude/cbb-web-fallback @ e35eaf8 -> T-Rank names).
# Any other name is BLOCKED by resolve_team(); do not guess.
DK_ALIASES = {"NIowa": "Northern Iowa", "Davidson": "Davidson", "StBona": "St. Bonaventure", "AppSt": "Appalachian St.",
              "OleMiss": "Mississippi", "Clemson": "Clemson", "UW": "Washington", "BYU": "BYU", "VCU": "VCU",
              "Prov": "Providence", "CSU": "Colorado St.", "Arizona": "Arizona"}

class Blocked(ValueError):
    pass

def resolve_team(name, rows):
    t = DK_ALIASES.get(name, name)
    if t not in rows: raise Blocked("UNRESOLVED_TEAM:" + str(name))
    return t

def _val(cell):
    parts = cell.strip().split()
    if not parts: raise Blocked("empty metric cell")
    x = float(parts[0].replace("+", ""))
    if not math.isfinite(x): raise Blocked("nonfinite metric")
    return x

def parse_league(text):
    m = _HEADER.search(text.replace("\n", " ").replace("\r", ""))
    if not m: raise Blocked("league header not found")
    oe, efg, tov, orb, ftr, p3, p3r, tempo = (float(x) for x in m.groups())
    if not (95 <= oe <= 115 and 60 <= tempo <= 75): raise Blocked("league constants outside plausible range")
    return dict(oe=oe, efg=efg/100, tov=tov/100, orb=orb/100, ftr=ftr/100, three_p=p3/100, three_pa_rate=p3r, tempo=tempo)

def clean_team(label):
    raw = label.strip(); name = _SUFFIX.sub("", raw).strip()
    if not name: raise Blocked("empty team label")
    return name, name != raw

def parse_rows(text):
    flat = text.replace("\r", "").replace("\n", "")
    rows, quarantine = {}, []
    for chunk in flat.split("||"):
        cells = chunk.strip().strip("|").split("|")
        if not cells or not cells[0].strip().isdigit(): continue
        try:
            if len(cells) != NCELL: raise Blocked(f"expected {NCELL} cells, got {len(cells)}")
            d = dict(zip(COLS, cells)); name, was = clean_team(d["team"]); g = int(d["g"])
            if not 1 <= g <= 60: raise Blocked("games out of range")
            r = dict(team=name, raw_label=d["team"].strip(), label_cleaned=was, conf=d["conf"].strip(), games=g, rank=int(d["rk"]))
            for k in COLS[5:]: r[k] = _val(d[k])
            if not (80 <= r["adjoe"] <= 140 and 80 <= r["adjde"] <= 140 and 55 <= r["adjt"] <= 85):
                raise Blocked("efficiency or tempo out of range")
            if name in rows: raise Blocked("duplicate team")
            rows[name] = r
        except (Blocked, ValueError) as e:
            quarantine.append(dict(row=chunk.strip()[:80], reason=str(e)))
    return rows, quarantine

def to_model_team(r):
    return dict(team=r["team"], games=float(r["games"]), adjoe=r["adjoe"], adjde=r["adjde"], adj_t=r["adjt"],
                efg_o=r["efg"], efg_d=r["efgd"], tov_o=r["tor"], tov_d=r["tord"], orb_o=r["orb"], orb_d=100.0 - r["drb"],
                ftr_o=r["ftr"], ftr_d=r["ftrd"], three_pa_rate=r["p3r"], three_p_o=r["p3"], three_p_d=r["p3d"])

def intake(text, capture_utc, tipoff_utc=None):
    cu = datetime.fromisoformat(capture_utc.replace("Z", "+00:00"))
    if cu.tzinfo is None: raise Blocked("capture time needs UTC offset")
    if tipoff_utc:
        if cu >= datetime.fromisoformat(tipoff_utc.replace("Z", "+00:00")): raise Blocked("capture at/after tipoff")
    league = parse_league(text); rows, q = parse_rows(text)
    if not rows: raise Blocked("no valid team rows")
    return dict(league=league, rows=rows, quarantine=q, capture_utc=capture_utc,
                source_text_sha256=hashlib.sha256(text.encode()).hexdigest(), provenance="EXTRACTED_TEXT_NOT_BYTE_AUTHENTICATED")
