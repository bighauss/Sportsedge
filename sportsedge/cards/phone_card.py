"""SportsEdge Munich-style phone card — safe, reproducible SVG + optional PNG.

No book URLs, source screenshots, raw private market boards or API keys are
published. The renderer only displays the exact supplied, pregame-authenticated
(or clearly PAPER) rows; it does NOT generate forecasts, quotes or EV.

Example:
 python -m sportsedge.cards.phone_card approved_private_card.json card.svg
 python -m sportsedge.cards.phone_card approved_private_card.json card.png

PNG requires optional CairoSVG. Source manifest and image/logo assets must
remain local/private; GitHub CI runs synthetic fixtures only.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re

W,H=1080,1920
COLORS={"bg":"#07111b","panel":"#101e2c","border":"#2a4855",
        "green":"#38f2b5","white":"#f7fbff","muted":"#a8bcc7",
        "amber":"#f9b34a","red":"#ff6778"}
NUM=re.compile(r"^-?(?:\d+)(?:\.\d+)?$")
HEX=re.compile(r"^[0-9a-f]{64}$")
MAXROWS=8


class InvalidCard(ValueError):
    pass


def utc(t):
    try:
        x=datetime.fromisoformat(t.replace("Z","+00:00"))
        if x.tzinfo is None:raise ValueError("No timezone")
        return x.astimezone(timezone.utc)
    except (AttributeError,ValueError) as ex:raise InvalidCard("Timestamp must be ISO 8601 with timezone") from ex


def finite(x, *, minimum=None, maximum=None):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x):
        raise InvalidCard("Nonfinite/non-numeric card value")
    if minimum is not None and x<minimum:raise InvalidCard("Card value below limit")
    if maximum is not None and x>maximum:raise InvalidCard("Card value above limit")
    return x


def clean_text(x,limit=48):
    if not isinstance(x,str) or not x or len(x)>limit or any(ord(c)<32 for c in x):
        raise InvalidCard("Card text invalid")
    return x


def embed_png(root,spec):
    if spec is None:
        return ""
    if not isinstance(spec,dict) or not set(("path","sha256","rights")).issubset(spec):
        raise InvalidCard("Logo requires path, SHA256 and usage rights")
    if spec["rights"] not in ("OWNER_PROVIDED","LICENSED_ASSET"):
        raise InvalidCard("Unverified logo rights")
    p=(root/spec["path"]).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise InvalidCard("Logo file outside private card folder")
    data=p.read_bytes()
    if (len(data)>512000 or data[:8]!=b"\x89PNG\r\n\x1a\n" or
            not HEX.fullmatch(spec["sha256"]) or
            hashlib.sha256(data).hexdigest()!=spec["sha256"]):
        raise InvalidCard("Invalid/corrupt/unverified PNG logo")
    return "data:image/png;base64,"+base64.b64encode(data).decode("ascii")


def validate_card(card,root):
    if not isinstance(card,dict):raise InvalidCard("Card must be JSON object")
    if card.get("release") not in ("PAPER_0U","NO_VERIFIED_PLAY","VALIDATED_RESEARCH"):
        raise InvalidCard("Unknown/nonadmitted card release state")
    if card["release"]=="VALIDATED_RESEARCH":
        # Even signed validation requires an external confirmation. The
        # card renderer cannot certify provider authentication or live EV.
        raise InvalidCard("Renderer cannot independently promote an official betting card")
    if not isinstance(card.get("source"),dict):raise InvalidCard("Model provenance required")
    src=card["source"]
    for k in ("model_sha256","feature_sha256","frozen_utc"):
        if k not in src:raise InvalidCard("Missing model provenance")
    if not HEX.fullmatch(src["model_sha256"]) or not HEX.fullmatch(src["feature_sha256"]):
        raise InvalidCard("Invalid code/feature SHA256")
    game=card.get("game")
    if not isinstance(game,dict):raise InvalidCard("Missing matchup")
    for k in ("sport","away_name","home_name","away_abbr","home_abbr",
              "venue","kickoff_utc","time_ct"):
        clean_text(game.get(k),64)
    if game["sport"] not in ("NFL","CFB","CBB","NBA","NHL","MLB"):
        raise InvalidCard("Unknown sport")
    kickoff=utc(game["kickoff_utc"])
    if utc(src["frozen_utc"])>=kickoff:raise InvalidCard("Model source frozen after start")
    if len(game["away_abbr"])>4 or len(game["home_abbr"])>4:
        raise InvalidCard("Team abbreviations too long")
    if game["away_abbr"]==game["home_abbr"]:
        raise InvalidCard("Duplicate teams")
    for k in ("away_projection","home_projection","total_projection"):
        finite(game[k],minimum=0,maximum=250)
    if abs((game["away_projection"]+game["home_projection"])-game["total_projection"])>.11:
        raise InvalidCard("Game total is inconsistent with projected scores")
    away_logo=embed_png(root,game.get("away_logo"))
    home_logo=embed_png(root,game.get("home_logo"))
    plays=card.get("plays",[])
    if not isinstance(plays,list) or len(plays)>MAXROWS:
        raise InvalidCard("Too many displayed plays")
    for i,p in enumerate(plays):
        if not isinstance(p,dict):raise InvalidCard("Bad market row")
        if p.get("rank")!=i+1:raise InvalidCard("Play ranks must be sequential")
        for k in ("play","market","game_time_ct"):
            clean_text(p.get(k),56)
        if p.get("status") not in ("PAPER_0U","BLOCKED"):
            raise InvalidCard("No authenticated OFFICIAL status may be asserted")
        if p["status"]=="BLOCKED":
            if any(k in p for k in ("price","win_probability","ev_estimate_pct","stars")):
                raise InvalidCard("Blocked row must not display playable price or EV")
            continue
        if card["release"]!="PAPER_0U":raise InvalidCard("PAPER rows require PAPER release")
        if not p.get("receipt_id") or not p.get("price_observed_utc"):
            raise InvalidCard("Price/receipt provenance absent")
        if utc(p["price_observed_utc"])>=kickoff or utc(p["price_observed_utc"])<utc(src["frozen_utc"]):
            raise InvalidCard("Offer not after model freeze/before kickoff")
        price=p.get("price")
        if isinstance(price,bool) or type(price)!=int or abs(price)<100 or abs(price)>20000:
            raise InvalidCard("Invalid American odds")
        finite(p.get("win_probability"),minimum=0,maximum=1)
        finite(p.get("ev_estimate_pct"),minimum=-100,maximum=1000)
        finite(p.get("projection"),minimum=0,maximum=500)
        if type(p.get("stars"))!=int or not 1<=p["stars"]<=5:
            raise InvalidCard("Invalid star rating")
    if any(p.get("status")=="PAPER_0U" for p in plays):
        values=[p["ev_estimate_pct"] for p in plays if p["status"]=="PAPER_0U"]
        if values!=sorted(values,reverse=True):
            raise InvalidCard("Research rows must be ranked by model-estimated EV")
    return away_logo,home_logo


def t(x,y,content,size=30,weight=500,color="#f7fbff",anchor="start",extra=""):
    return (f'<text x="{x}" y="{y}" font-family="DejaVu Sans,Arial,sans-serif" '
            f'font-weight="{weight}" font-size="{size}" fill="{color}" '
            f'text-anchor="{anchor}" {extra}>{escape(str(content))}</text>')


def fmt_score(x):
    return f"{x:.1f}"


def glyph(name,x,y,logo,abbr):
    if logo:
        return (f'<circle cx="{x}" cy="{y}" r="76" fill="#102a39" stroke="#38f2b5" stroke-width="3"/>'
                f'<image x="{x-67}" y="{y-67}" width="134" height="134" '
                f'preserveAspectRatio="xMidYMid meet" href="{logo}"/>')
    return (f'<circle cx="{x}" cy="{y}" r="76" fill="#102a39" stroke="#38f2b5" stroke-width="3"/>'
            +t(x,y+16,abbr,size=43,weight=850,anchor="middle"))


def render(card,root):
    away_logo,home_logo=validate_card(card,root)
    g=card["game"]
    out=[
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#091728"/>'
        '<stop offset="1" stop-color="#021216"/></linearGradient>'
        '<pattern id="turf" width="96" height="96" patternUnits="userSpaceOnUse">'
        '<path d="M0 0 L96 96 M96 0 L0 96" stroke="#184438" stroke-width="1" opacity=".28"/>'
        '</pattern></defs>',
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
        '<rect width="1080" height="1920" fill="url(#turf)"/>',
        '<path d="M70 160H1010" stroke="#38f2b5" stroke-width="5"/>',
        t(70,112,"SPORTSEDGE",size=64,weight=900,color=COLORS["white"]),
        t(1010,110,g["sport"]+"  RUN IT",size=32,weight=700,color=COLORS["green"],anchor="end"),
        t(540,225,g["venue"].upper(),size=26,color=COLORS["muted"],weight=650,anchor="middle"),
        t(540,272,g["time_ct"],size=32,color=COLORS["green"],weight=800,anchor="middle"),
        '<rect x="65" y="320" width="950" height="430" rx="28" fill="#102333" stroke="#27534c" stroke-width="3"/>',
        glyph("away",267,445,away_logo,g["away_abbr"]),
        glyph("home",812,445,home_logo,g["home_abbr"]),
        t(267,572,g["away_name"],size=34,weight=750,anchor="middle"),
        t(812,572,g["home_name"],size=34,weight=750,anchor="middle"),
        t(540,456,"@",size=80,weight=300,color=COLORS["muted"],anchor="middle"),
        t(540,647,"MODEL PROJECTION",size=25,weight=700,color=COLORS["green"],anchor="middle"),
        t(269,715,fmt_score(g["away_projection"]),size=63,weight=900,anchor="middle"),
        t(812,715,fmt_score(g["home_projection"]),size=63,weight=900,anchor="middle"),
        t(540,711,"TOTAL "+fmt_score(g["total_projection"]),size=24,weight=750,color=COLORS["muted"],anchor="middle"),
        t(68,831,"RANKED RESEARCH CARD",size=37,weight=850),
        t(1010,832,"CT",size=26,color=COLORS["green"],anchor="end"),
        '<rect x="64" y="866" width="952" height="72" rx="11" fill="#203544"/>',
        t(87,909,"#",size=26,weight=750,color=COLORS["muted"]),
        t(155,909,"PLAY",size=26,weight=750,color=COLORS["muted"]),
        t(594,909,"PRICE",size=23,weight=750,color=COLORS["muted"],anchor="middle"),
        t(703,909,"PROJ",size=23,weight=750,color=COLORS["muted"],anchor="middle"),
        t(804,909,"EV EST.",size=22,weight=750,color=COLORS["muted"],anchor="middle"),
        t(971,909,"RATING",size=20,weight=750,color=COLORS["muted"],anchor="end"),
    ]
    for i,p in enumerate(card["plays"]):
        y=967+i*109
        if i%2==0:
            out.append(f'<rect x="64" y="{y-25}" width="952" height="99" rx="12" fill="#132737"/>')
        out.append(t(90,y+20,str(i+1),size=30,weight=800,color=COLORS["green"]))
        title=p["play"][:27]
        out.append(t(155,y+10,title,size=27,weight=650))
        out.append(t(155,y+43,p["game_time_ct"],size=20,color=COLORS["muted"]))
        if p["status"]=="BLOCKED":
            out.append(t(787,y+20,"NO DATA",size=28,color=COLORS["amber"],anchor="middle"))
            continue
        price=p["price"]
        out.append(t(594,y+20,("+" if price>0 else "")+str(price),size=27,weight=700,anchor="middle"))
        out.append(t(703,y+20,fmt_score(p["projection"]),size=26,weight=700,anchor="middle"))
        out.append(t(804,y+20,("%+.1f" % p["ev_estimate_pct"])+"%",size=26,weight=800,color=COLORS["green"],anchor="middle"))
        out.append(t(990,y+17,"★"*p["stars"],size=18,weight=600,color=COLORS["amber"],anchor="end"))
        out.append(t(990,y+48,("%.1f" % (p["win_probability"]*100))+"% Win",size=17,color=COLORS["muted"],anchor="end"))
    out.extend([
        '<path d="M68 1818H1010" stroke="#285b50" stroke-width="2"/>',
        t(68,1860,"RESEARCH ONLY • UNVALIDATED ESTIMATES • 0u",size=23,weight=670,color=COLORS["muted"]),
        t(1010,1886,g["away_abbr"]+" @ "+g["home_abbr"],size=22,color=COLORS["muted"],anchor="end"),
        '</svg>'
    ])
    return "\n".join(out)


def private_output_path(candidate):
    """Never publish private model/odds evidence into the public checkout.

    Symlink-aware and anchored to this module's repository root, not CWD.
    Existing files are never replaced, including an existing symlink.
    """
    destination=Path(candidate)
    if destination.is_symlink():
        raise InvalidCard("Refusing symlinked card destination")
    resolved=destination.resolve()
    repo=Path(__file__).resolve().parents[2]
    if resolved==repo or repo in resolved.parents:
        raise InvalidCard("Cards must be rendered outside the public repository")
    if destination.exists():
        raise InvalidCard("Existing card evidence cannot be overwritten")
    return destination


def main():
    p=argparse.ArgumentParser()
    p.add_argument("card_json",type=Path)
    p.add_argument("output",type=Path)
    a=p.parse_args()
    if a.output.suffix.lower() not in (".svg",".png"):
        raise InvalidCard("Only .svg or .png outputs supported")
    output=private_output_path(a.output)
    root=a.card_json.resolve().parent
    repo=Path(__file__).resolve().parents[2]
    if a.card_json.resolve()==repo or repo in a.card_json.resolve().parents:
        raise InvalidCard("Private source card JSON must not live in public GitHub")
    card=json.loads(a.card_json.read_text(encoding="utf-8"))
    markup=render(card,root)
    rendered=None
    if output.suffix.lower()==".png":
        try:import cairosvg
        except ImportError as e:
            raise InvalidCard("PNG requires optional CairoSVG: pip install cairosvg") from e
        # Generate the whole PNG before opening the destination: failed raster
        # conversion must not create a misleading partial research card.
        rendered=cairosvg.svg2png(bytestring=markup.encode(),
                                 output_width=W,output_height=H)
    output.parent.mkdir(parents=True,exist_ok=True)
    # Binary exclusive-create also protects against another writer between
    # the existence preflight and actual output. Never overwrite old cards.
    with output.open("xb") as handle:
        handle.write(rendered if rendered is not None else markup.encode("utf-8"))
    print(json.dumps({"status":"RESEARCH_ONLY","output":str(output),
                      "ranked_rows":len(card["plays"]),"automatic_bet_placement":False}))


if __name__=="__main__":
    main()
